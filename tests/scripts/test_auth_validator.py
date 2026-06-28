from __future__ import annotations

import pytest
from scripts.auth_validator import AuthValidationResult, _normalize_scopes, validate_auth_payload


class TestNormalizeScopes:
    """Test suite for auth scope normalization."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (" repo , read , , write ", frozenset({"repo", "read", "write"})),
            (["repo", " read ", "", None, 42], frozenset({"repo", "read", "None", "42"})),
            (("repo", "repo", "write"), frozenset({"repo", "write"})),
            ({"repo", "read"}, frozenset({"repo", "read"})),
            (frozenset({"repo", "write"}), frozenset({"repo", "write"})),
            ("", frozenset()),
            (None, None),
            ({"repo": True}, None),
            (object(), None),
        ],
    )
    def test_normalize_scopes_contract(
        self, value: object, expected: frozenset[str] | None
    ) -> None:
        assert _normalize_scopes(value) == expected


class TestValidateAuthPayload:
    """Test suite for validate_auth_payload function."""

    def test_missing_payload_returns_invalid_result(self) -> None:
        """Test that None payload returns invalid result with missing_payload error."""
        result = validate_auth_payload(None)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_payload"
        assert result.message == "Missing authentication payload."
        assert result.scopes is None
        assert result.allowed_scopes is None
        assert result.missing_fields == ("payload",)
        assert result.extra_scopes == ()

    def test_non_dict_payload_returns_invalid_result(self) -> None:
        """Test that non-dict payload returns invalid result with invalid_payload error."""
        result = validate_auth_payload("not_a_dict")

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "invalid_payload"
        assert result.message == "Authentication payload must be a mapping."
        assert result.scopes is None
        assert result.allowed_scopes is None
        assert result.missing_fields == ("payload",)
        assert result.extra_scopes == ()

    def test_missing_scopes_field_returns_invalid_result(self) -> None:
        """Test that missing scopes field returns invalid result."""
        payload = {"allowed_scopes": "repo,read"}
        result = validate_auth_payload(payload)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_fields"
        assert result.message == "Authentication payload missing fields: scopes."
        assert result.scopes is None
        assert result.allowed_scopes is None
        assert result.missing_fields == ("scopes",)
        assert result.extra_scopes == ()

    def test_missing_allowed_scopes_field_returns_invalid_result(self) -> None:
        """Test that missing allowed_scopes field returns invalid result."""
        payload = {"scopes": "repo,write"}
        result = validate_auth_payload(payload)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_fields"
        assert result.message == "Authentication payload missing fields: allowed_scopes."
        assert result.scopes is None
        assert result.allowed_scopes is None
        assert result.missing_fields == ("allowed_scopes",)
        assert result.extra_scopes == ()

    def test_missing_both_fields_returns_invalid_result(self) -> None:
        """Test that missing both scopes and allowed_scopes fields returns invalid result."""
        payload = {"other_field": "value"}
        result = validate_auth_payload(payload)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_fields"
        assert "scopes" in result.message and "allowed_scopes" in result.message
        assert result.scopes is None
        assert result.allowed_scopes is None
        assert set(result.missing_fields) == {"scopes", "allowed_scopes"}
        assert result.extra_scopes == ()

    def test_none_scopes_with_allowed_scopes_returns_skipped(self) -> None:
        """Test that None scopes with allowed_scopes returns skipped result."""
        payload = {"scopes": None, "allowed_scopes": "repo,read"}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is True
        assert result.error == "unknown_scopes"
        assert result.message == "Unable to determine token scopes; skipping scope check."
        assert result.scopes is None
        assert result.allowed_scopes == frozenset({"repo", "read"})
        assert result.missing_fields == ()
        assert result.extra_scopes == ()

    def test_missing_allowed_scopes_with_require_allowed_scopes_false(self) -> None:
        """Test that missing allowed_scopes with require_allowed_scopes=False returns skipped."""
        payload = {"scopes": "repo,write", "allowed_scopes": ""}
        result = validate_auth_payload(payload, require_allowed_scopes=False)

        assert result.valid is True
        assert result.skipped is True
        assert result.error == "missing_allowed_scopes"
        assert result.message == "Allowed scopes missing; skipping scope validation."
        assert result.scopes == frozenset({"repo", "write"})
        assert result.allowed_scopes == frozenset()
        assert result.missing_fields == ()
        assert result.extra_scopes == ()

    def test_missing_allowed_scopes_with_require_allowed_scopes_true(self) -> None:
        """Test that missing allowed_scopes with require_allowed_scopes=True returns invalid."""
        payload = {"scopes": "repo,write", "allowed_scopes": ""}
        result = validate_auth_payload(payload, require_allowed_scopes=True)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_allowed_scopes"
        assert result.message == "Allowed scopes are required for validation."
        assert result.scopes == frozenset({"repo", "write"})
        assert result.allowed_scopes == frozenset()
        assert result.missing_fields == ()
        assert result.extra_scopes == ()

    def test_extra_scopes_detected(self) -> None:
        """Test that extra scopes are detected and returned as invalid."""
        payload = {"scopes": "repo,write,admin", "allowed_scopes": "repo,read"}
        result = validate_auth_payload(payload)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "extra_scopes"
        assert "admin, write" in result.message
        assert "Allowed: read, repo" in result.message
        assert result.scopes == frozenset({"repo", "write", "admin"})
        assert result.allowed_scopes == frozenset({"repo", "read"})
        assert result.extra_scopes == ("admin", "write")

    def test_missing_required_scopes_with_require_all_scopes_true(self) -> None:
        """Test that missing required scopes with require_all_scopes=True returns invalid."""
        payload = {"scopes": "repo,read", "allowed_scopes": "repo,read,write"}
        result = validate_auth_payload(payload, require_all_scopes=True)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_scopes"
        assert "Missing: write" in result.message
        assert "Required: read, repo, write" in result.message
        assert result.scopes == frozenset({"repo", "read"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write"})

    def test_missing_required_scopes_with_require_all_scopes_false(self) -> None:
        """Test that missing required scopes with require_all_scopes=False returns valid."""
        payload = {"scopes": "repo,read", "allowed_scopes": "repo,read,write"}
        result = validate_auth_payload(payload, require_all_scopes=False)

        assert result.valid is True
        assert result.skipped is False
        assert result.error is None
        assert result.message is None
        assert result.scopes == frozenset({"repo", "read"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write"})
        assert result.extra_scopes == ()

    def test_valid_scopes_exact_match(self) -> None:
        """Test that exact match of scopes and allowed_scopes returns valid."""
        payload = {"scopes": "repo,read,write", "allowed_scopes": "repo,read,write"}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is False
        assert result.error is None
        assert result.message is None
        assert result.scopes == frozenset({"repo", "read", "write"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write"})
        assert result.extra_scopes == ()

    def test_valid_scopes_subset_when_full_scope_set_not_required(self) -> None:
        """Test that subsets are valid when require_all_scopes is disabled."""
        payload = {"scopes": "repo", "allowed_scopes": "repo,read,write,admin"}
        result = validate_auth_payload(payload, require_all_scopes=False)

        assert result.valid is True
        assert result.skipped is False
        assert result.error is None
        assert result.message is None
        assert result.scopes == frozenset({"repo"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write", "admin"})
        assert result.extra_scopes == ()

    def test_scopes_as_list(self) -> None:
        """Test that scopes provided as list are normalized correctly."""
        payload = {"scopes": ["repo", "read", "write"], "allowed_scopes": ["repo", "read", "write"]}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is False
        assert result.scopes == frozenset({"repo", "read", "write"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write"})

    def test_scopes_as_set(self) -> None:
        """Test that scopes provided as set are normalized correctly."""
        payload = {"scopes": {"repo", "read"}, "allowed_scopes": frozenset({"repo", "read"})}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is False
        assert result.scopes == frozenset({"repo", "read"})
        assert result.allowed_scopes == frozenset({"repo", "read"})

    def test_scopes_with_whitespace(self) -> None:
        """Test that scopes with whitespace are normalized correctly."""
        payload = {"scopes": " repo , read , write ", "allowed_scopes": "repo,read,write"}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is False
        assert result.scopes == frozenset({"repo", "read", "write"})
        assert result.allowed_scopes == frozenset({"repo", "read", "write"})

    def test_scopes_with_empty_strings(self) -> None:
        """Test that empty strings in scopes are handled correctly."""
        payload = {"scopes": "repo,,read,,", "allowed_scopes": "repo,read"}
        result = validate_auth_payload(payload)

        assert result.valid is True
        assert result.skipped is False
        assert result.scopes == frozenset({"repo", "read"})
        assert result.allowed_scopes == frozenset({"repo", "read"})

    def test_empty_scopes_string_reports_missing_required_scopes(self) -> None:
        """Test that an empty scopes string is treated as no granted scopes."""
        payload = {"scopes": "", "allowed_scopes": "repo,read"}
        result = validate_auth_payload(payload)

        assert result.valid is False
        assert result.skipped is False
        assert result.error == "missing_scopes"
        assert result.scopes == frozenset()
        assert result.allowed_scopes == frozenset({"repo", "read"})

    def test_empty_allowed_scopes_string(self) -> None:
        """Test that empty allowed_scopes string with require_allowed_scopes=False skips."""
        payload = {"scopes": "repo,read", "allowed_scopes": ""}
        result = validate_auth_payload(payload, require_allowed_scopes=False)

        assert result.valid is True
        assert result.skipped is True
        assert result.error == "missing_allowed_scopes"


class TestAuthValidationResult:
    """Test suite for AuthValidationResult dataclass."""

    def test_result_immutability(self) -> None:
        """Test that AuthValidationResult is immutable (frozen)."""
        result = AuthValidationResult(
            valid=True,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )

        with pytest.raises(AttributeError):
            result.valid = False  # type: ignore

    def test_result_equality(self) -> None:
        """Test that AuthValidationResult instances with same values are equal."""
        result1 = AuthValidationResult(
            valid=True,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )
        result2 = AuthValidationResult(
            valid=True,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )

        assert result1 == result2

    def test_result_inequality(self) -> None:
        """Test that AuthValidationResult instances with different values are not equal."""
        result1 = AuthValidationResult(
            valid=True,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )
        result2 = AuthValidationResult(
            valid=False,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )

        assert result1 != result2

    def test_result_hashable(self) -> None:
        """Test that AuthValidationResult is hashable."""
        result = AuthValidationResult(
            valid=True,
            skipped=False,
            error=None,
            message=None,
            scopes=frozenset({"repo"}),
            allowed_scopes=frozenset({"repo", "read"}),
            extra_scopes=(),
            missing_fields=(),
        )

        # Should be able to use in a set
        result_set = {result}
        assert result in result_set

        # Should be able to use as dict key
        result_dict = {result: "test"}
        assert result_dict[result] == "test"
