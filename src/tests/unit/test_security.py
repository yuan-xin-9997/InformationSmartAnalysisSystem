"""Security unit tests: password.txt parsing, hashing, JWT, masking."""
from __future__ import annotations


def test_parse_password_file(tmp_path):
    from app.backend.core.security import parse_password_file

    p = tmp_path / "pw.txt"
    p.write_text(
        "# comment\nadmin:admin123:admin\nuser:p@ss:user\n\nbadline\n", encoding="utf-8"
    )
    entries = parse_password_file(p)
    assert ("admin", "admin123", "admin") in entries
    assert ("user", "p@ss", "user") in entries
    assert len(entries) == 2  # blank + bad lines skipped


def test_parse_password_file_with_colon_in_password(tmp_path):
    from app.backend.core.security import parse_password_file

    p = tmp_path / "pw.txt"
    p.write_text("u:a:b:c:user\n", encoding="utf-8")
    entries = parse_password_file(p)
    assert entries == [("u", "a:b:c", "user")]


def test_parse_missing_file(tmp_path):
    from app.backend.core.security import parse_password_file

    assert parse_password_file(tmp_path / "nope.txt") == []


def test_password_hash_and_verify():
    from app.backend.core.security import hash_password, verify_password

    h = hash_password("secret")
    assert h != "secret"
    assert verify_password("secret", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    from app.backend.core.security import create_access_token, decode_access_token

    token = create_access_token("alice", "admin")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["role"] == "admin"


def test_jwt_invalid_returns_none():
    from app.backend.core.security import decode_access_token

    assert decode_access_token("garbage.token.here") is None


def test_mask_sensitive():
    from app.backend.core.secrets import mask_sensitive

    out = mask_sensitive(
        {"api_key": "abcd1234efgh", "name": "x", "nested": {"api_token": "tok1234"}}
    )
    assert out["api_key"] == "******efgh"
    assert out["name"] == "x"
    assert out["nested"]["api_token"] == "******1234"
    # placeholder text (non-ascii tail) -> fully masked
    assert mask_sensitive({"api_key": "请替换"})["api_key"] == "******"
