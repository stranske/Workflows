from scripts.auth_validator import validate_auth_payload


def test_validate_auth_payload_none() -> None:
    result = validate_auth_payload(None)

    assert result.valid is False
    assert result.skipped is False
    assert result.error == "missing_payload"
    assert result.message == "Missing authentication payload."
    assert result.missing_fields == ("payload",)
    assert result.scopes is None
    assert result.allowed_scopes is None


def test_validate_auth_payload_empty_mapping() -> None:
    result = validate_auth_payload({})

    assert result.valid is False
    assert result.skipped is False
    assert result.error == "missing_fields"
    assert result.message == "Authentication payload missing fields: scopes, allowed_scopes."
    assert result.missing_fields == ("scopes", "allowed_scopes")
    assert result.scopes is None
    assert result.allowed_scopes is None


def test_validate_auth_payload_unknown_scopes() -> None:
    result = validate_auth_payload({"scopes": None, "allowed_scopes": {"repo"}})

    assert result.valid is True
    assert result.skipped is True
    assert result.error == "unknown_scopes"
    assert result.message == "Unable to determine token scopes; skipping scope check."
    assert result.allowed_scopes == frozenset({"repo"})


def test_validate_auth_payload_missing_allowed_scopes() -> None:
    result = validate_auth_payload({"scopes": {"repo"}, "allowed_scopes": []})

    assert result.valid is False
    assert result.skipped is False
    assert result.error == "missing_allowed_scopes"
    assert result.message == "Allowed scopes are required for validation."


def test_validate_auth_payload_extra_scopes() -> None:
    result = validate_auth_payload({"scopes": {"repo", "admin:org"}, "allowed_scopes": {"repo"}})

    assert result.valid is False
    assert result.skipped is False
    assert result.error == "extra_scopes"
    assert "Token scopes exceed allowed scopes." in (result.message or "")
    assert result.extra_scopes == ("admin:org",)


def test_validate_auth_payload_missing_scopes() -> None:
    result = validate_auth_payload({"scopes": {"repo"}, "allowed_scopes": {"repo", "public_repo"}})

    assert result.valid is False
    assert result.skipped is False
    assert result.error == "missing_scopes"
    assert "Token scopes missing required scopes." in (result.message or "")


def test_validate_auth_payload_success() -> None:
    result = validate_auth_payload({"scopes": {"repo"}, "allowed_scopes": {"repo"}})

    assert result.valid is True
    assert result.skipped is False
    assert result.error is None
    assert result.message is None
