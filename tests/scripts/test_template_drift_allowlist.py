from __future__ import annotations

import collections
import configparser
import re
from pathlib import Path

from scripts.check_template_drift import read_allowlist

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "config/template-drift-allowlist.txt"

# The prose records a REVIEW as a verb followed by a date: "re-reviewed 2026-06-20",
# "re-baselined 2026-06-30", "updated 2026-08-05", "reviewed 2026-08-21". A bare date
# is NOT a review — most of these rationales open with a mechanical event ("client-id
# rename 2026-08-24: ... the divergence itself is unchanged and was NOT re-reviewed"),
# and reading that date as a review is exactly the conflation this file now forbids.
# The rationales are layered newest-first, so the FIRST match is the most recent review.
_REVIEW_DATE = re.compile(
    r"(?:re-reviewed|reviewed|re-baselined|baselined|updated)\s+(20\d\d-\d\d-\d\d)",
    re.IGNORECASE,
)

# At most this many pairs may leave their review date unstated in prose. It is not
# zero because one pair's rationale is entirely fingerprint refreshes and the
# Non-Goals forbid rewriting the twenty rationales; it is not unbounded because
# "the prose says nothing" must not become the way every pair escapes the check.
MAX_PAIRS_WITHOUT_A_STATED_REVIEW = 1


def stated_review_date(divergence: str) -> str | None:
    """The review date this rationale states, or None when it states none."""
    match = _REVIEW_DATE.search(divergence)
    return match.group(1) if match else None


def _pairs() -> dict[str, configparser.SectionProxy]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ALLOWLIST, encoding="utf-8")
    return {section: parser[section] for section in parser.sections()}


def test_every_pair_states_its_divergence() -> None:
    """Each pair's `divergence_reviewed` must equal the date its own prose records.

    Non-emptiness was the old assertion, and a blanket `divergence_reviewed = <today>`
    on all twenty pairs passed it. The field is only worth having if it can be checked
    against something, and the only independent source is the rationale beside it.
    """
    pairs = _pairs()
    assert ALLOWLIST.name == "template-drift-allowlist.txt"
    assert len(pairs) >= 1

    unstated: list[str] = []
    mismatched: list[str] = []
    for section, entry in pairs.items():
        divergence = entry.get("divergence", "").strip()
        reviewed = entry.get("divergence_reviewed", "").strip()
        refreshed = entry.get("fingerprint_refreshed", "").strip()
        assert divergence and "Existing reviewed baseline drift" not in divergence
        assert re.fullmatch(r"20\d\d-\d\d-\d\d", reviewed), (
            f"{section}: divergence_reviewed must be an ISO date, got {reviewed!r}"
        )
        assert re.fullmatch(r"20\d\d-\d\d-\d\d", refreshed), (
            f"{section}: fingerprint_refreshed must be an ISO date, got {refreshed!r}"
        )

        stated = stated_review_date(divergence)
        if stated is None:
            unstated.append(section)
        elif stated != reviewed:
            mismatched.append(
                f"{section}: prose records a review on {stated}, "
                f"divergence_reviewed says {reviewed}"
            )

    assert mismatched == [], (
        "divergence_reviewed disagrees with the pair's own rationale:\n"
        + "\n".join(mismatched)
    )
    assert len(unstated) <= MAX_PAIRS_WITHOUT_A_STATED_REVIEW, (
        f"{len(unstated)} pairs state no review date in their rationale, so their "
        f"divergence_reviewed cannot be checked against anything: {unstated}"
    )


def test_divergence_reviewed_is_not_a_blanket_stamp() -> None:
    """No single `divergence_reviewed` value may cover half the pairs or more.

    Twenty pairs carrying one date is not twenty reviews on one day; it is one write
    asserting twenty judgements. Measured before this fix: 19 of 20 read 2026-08-23.
    """
    pairs = _pairs()
    counts = collections.Counter(
        entry.get("divergence_reviewed", "").strip() for entry in pairs.values()
    )
    value, multiplicity = counts.most_common(1)[0]
    assert multiplicity < len(pairs) / 2, (
        f"{multiplicity} of {len(pairs)} pairs share divergence_reviewed = {value!r}; "
        "that is a blanket stamp, not a per-pair review"
    )


def test_divergence_reviewed_is_not_a_copy_of_fingerprint_refreshed() -> None:
    """The two dates may coincide only when the pair's own prose names that date.

    A mechanical hash refresh must not be able to move the review claim. Equal dates
    are allowed where a genuine same-day review is recorded in the rationale, and
    forbidden where the only evidence is that the fingerprint moved.
    """
    offenders = []
    for section, entry in _pairs().items():
        reviewed = entry.get("divergence_reviewed", "").strip()
        refreshed = entry.get("fingerprint_refreshed", "").strip()
        if reviewed != refreshed:
            continue
        if stated_review_date(entry.get("divergence", "")) == reviewed:
            continue
        offenders.append(
            f"{section}: divergence_reviewed == fingerprint_refreshed == {reviewed}, "
            "and the rationale does not record a review on that date"
        )

    assert offenders == [], (
        "a fingerprint refresh appears to have carried the review claim with it:\n"
        + "\n".join(offenders)
    )


def test_review_date_parser_reads_the_verb_not_a_bare_date() -> None:
    """The parser must not treat a mechanical event's date as a review."""
    assert stated_review_date("Intentional divergence re-reviewed 2026-06-20: ...") == (
        "2026-06-20"
    )
    assert stated_review_date("Intentional divergence (re-baselined 2026-07-14): ...") == (
        "2026-07-14"
    )
    assert stated_review_date("... last updated 2026-08-05 ...") == "2026-08-05"

    # A bare date with no review verb is not a review.
    assert stated_review_date("client-id rename 2026-08-24: fingerprints refreshed") is None
    assert stated_review_date("no dates at all here") is None

    # Layered rationales are newest-first, so the FIRST review verb wins.
    layered = (
        "Named-secrets rollout 2026-08-23: applied identically. "
        "Prior divergence unchanged: Intentional divergence re-reviewed 2026-08-16: ..."
    )
    assert stated_review_date(layered) == "2026-08-16"


def test_read_allowlist_prefers_divergence_and_supports_legacy_reason(tmp_path: Path) -> None:
    allowlist_path = tmp_path / "allowlist.txt"
    allowlist_path.write_text(
        """
[pair.current]
main = root.yml
template = template.yml
main_sha256 = main-current
template_sha256 = template-current
divergence = current rationale
reason = superseded legacy rationale

[pair.legacy]
main = legacy-root.yml
template = legacy-template.yml
main_sha256 = main-legacy
template_sha256 = template-legacy
reason = legacy rationale
""".strip() + "\n",
        encoding="utf-8",
    )

    entries = read_allowlist(allowlist_path).entries

    assert [entry.reason for entry in entries] == ["current rationale", "legacy rationale"]
