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
