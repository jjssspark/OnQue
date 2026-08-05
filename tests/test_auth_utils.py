from auth import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_password_and_verify_roundtrip():
    hashed = hash_password("s3cr3t-pass")
    assert hashed != "s3cr3t-pass"
    assert verify_password("s3cr3t-pass", hashed) is True
    assert verify_password("wrong-pass", hashed) is False


def test_create_and_decode_access_token_roundtrip():
    token = create_access_token(user_id=42)
    assert decode_access_token(token) == 42


def test_decode_access_token_rejects_garbage():
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-real-token")
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "AUTH_TOKEN_INVALID"
