from engine.secret_ops import audit_secret_status


def test_secret_audit_writes_status(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "set")
    payload = audit_secret_status(root=tmp_path)

    assert any(item["name"] == "TELEGRAM_BOT_TOKEN" and item["present"] for item in payload["secrets"])
    assert (tmp_path / "runtime" / "reports" / "secret_status.json").exists()
