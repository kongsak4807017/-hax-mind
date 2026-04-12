from pathlib import Path

from engine.restart_manager import request_bot_restart


def test_request_bot_restart_launches_restart_script(tmp_path: Path, monkeypatch) -> None:
    script = tmp_path / "scripts" / "restart-telegram-bot.ps1"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("Write-Host 'restart'\n", encoding="utf-8")

    captured = {}

    class DummyPopen:
        def __init__(self, cmd, cwd=None):
            captured["cmd"] = cmd
            captured["cwd"] = cwd

    monkeypatch.setattr("engine.restart_manager.subprocess.Popen", DummyPopen)

    result = request_bot_restart(root=tmp_path, delay_seconds=3)

    assert result["status"] == "scheduled"
    assert result["delay_seconds"] == "3"
    assert captured["cwd"] == str(tmp_path)
    assert "restart-telegram-bot.ps1" in " ".join(captured["cmd"])
