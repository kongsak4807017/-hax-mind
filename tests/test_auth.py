from engine.auth import auth_status_for_user, is_authorized_user


def test_auth_allows_all_when_allowlist_empty(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_IDS", raising=False)
    assert is_authorized_user(123) is True
    status = auth_status_for_user(123)
    assert status.allowlist_enabled is False
    assert status.authorized is True


def test_auth_allowlist(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123, 456, invalid")
    assert is_authorized_user(123) is True
    assert is_authorized_user(999) is False
    status = auth_status_for_user(999)
    assert status.allowlist_enabled is True
    assert status.allowed_count == 2
    assert status.authorized is False
