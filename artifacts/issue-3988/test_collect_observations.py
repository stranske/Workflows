"""Focused saved-history classification tests; no GitHub or git calls."""

import copy
import unittest

from collect_observations import END, STATUS_LABELS, classify_record

BEFORE = "2026-11-08T00:00:00Z"
EARLIER = "2026-11-07T03:00:00Z"


def event(label, timestamp=BEFORE, action="labeled", event_id=1):
    return {"id": event_id, "event": action, "label": label, "created_at": timestamp}


def record(*events):
    return {
        "repository": "stranske/Workflows",
        "number": 1,
        "url": "https://github.com/stranske/Workflows/pull/1",
        "created_at": EARLIER,
        "history_complete": True,
        "label_events": [event("agents:keepalive", EARLIER), *events],
    }


class ClassificationTests(unittest.TestCase):
    def test_routing_at_end_is_excluded(self):
        kind, item = classify_record(record(event("agent:claude", END)))
        assert kind == "eligible"
        self.assertEqual(item["routing_status"], "absent")
        self.assertFalse(item["non_codex"])

    def test_keepalive_at_end_is_excluded(self):
        data = record()
        data["label_events"] = [event("agents:keepalive", END)]
        self.assertEqual(classify_record(data)[0], "excluded")

    def test_mixed_codex_non_codex_tie_is_conservative(self):
        for labels in [("agent:codex", "agent:claude"), ("agent:claude", "agent:codex")]:
            with self.subTest(labels=labels):
                _, item = classify_record(
                    record(*(event(label, event_id=i) for i, label in enumerate(labels)))
                )
                self.assertEqual(item["routing_status"], "ambiguous")
                self.assertEqual(item["tied_first_labels"], ["agent:claude", "agent:codex"])
                self.assertFalse(item["non_codex"])

    def test_auto_only_counts_for_label_measure(self):
        _, item = classify_record(record(event("agent:auto")))
        self.assertTrue(item["non_codex"])
        self.assertIsNone(item["first_concrete_routing_event"])
        self.assertFalse(item["concrete_non_codex"])

    def test_absent_routing_remains_eligible(self):
        kind, item = classify_record(record())
        assert kind == "eligible"
        self.assertEqual(item["routing_status"], "absent")
        self.assertFalse(item["non_codex"])

    def test_removed_labels_retain_historical_assignment(self):
        data = record(
            event("agent:claude", EARLIER),
            event("agent:claude", action="unlabeled"),
            event("agents:keepalive", action="unlabeled"),
        )
        before = copy.deepcopy(data)
        kind, item = classify_record(data)
        assert kind == "eligible"
        self.assertTrue(item["non_codex"])
        self.assertEqual(data, before)

    def test_status_before_codex_is_not_routing(self):
        for label in STATUS_LABELS:
            with self.subTest(label=label):
                _, item = classify_record(record(event(label, EARLIER), event("agent:codex")))
                self.assertEqual(item["first_routing_event"]["label"], "agent:codex")
                self.assertEqual(item["tied_first_labels"], ["agent:codex"])
                self.assertFalse(item["non_codex"])

    def test_consumer_agent_is_preserved(self):
        _, item = classify_record(record(event("agent:consumer-runner")))
        self.assertTrue(item["non_codex"])

    def test_incomplete_history_is_unknown(self):
        data = record(event("agent:claude"))
        data["history_complete"] = False
        self.assertEqual(classify_record(data)[0], "unknown")

    def test_explicit_end_boundary(self):
        self.assertEqual(classify_record(record(), end=EARLIER)[0], "excluded")


if __name__ == "__main__":
    unittest.main()
