from pathlib import Path

from engine.setup_wizard import (
    OPENROUTER_DEFAULTS,
    detect_env_file,
    ensure_env_file,
    format_setup_menu,
    get_setup_mode,
    openrouter_configured,
    upsert_env_values,
)


def test_get_setup_mode_accepts_key_and_slug() -> None:
    assert get_setup_mode("1").slug == "quick"
    assert get_setup_mode("production").key == "3"


def test_format_setup_menu_mentions_all_modes() -> None:
    menu = format_setup_menu()
    assert "Quick local setup" in menu
    assert "Telegram bot setup" in menu
    assert "Local production setup" in menu
    assert "Repair / re-check current install" in menu


def test_ensure_env_file_copies_template_when_missing(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("TELEGRAM_BOT_TOKEN=PUT_YOUR_BOT_TOKEN_HERE\n", encoding="utf-8")

    created = ensure_env_file(tmp_path)

    assert created == tmp_path / ".env"
    assert created.read_text(encoding="utf-8").startswith("TELEGRAM_BOT_TOKEN=")


def test_ensure_env_file_prefers_existing_env(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("from-template\n", encoding="utf-8")
    env = tmp_path / ".env.txt"
    env.write_text("already-set\n", encoding="utf-8")

    detected = detect_env_file(tmp_path)
    created = ensure_env_file(tmp_path)

    assert detected == env
    assert created == env
    assert not (tmp_path / ".env").exists()


def test_upsert_env_values_updates_existing_keys_and_appends_new_ones(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("A=1\nB=2\n", encoding="utf-8")

    upsert_env_values(env, {"B": "22", "OPENROUTER_MODEL": OPENROUTER_DEFAULTS["OPENROUTER_MODEL"]})

    content = env.read_text(encoding="utf-8")
    assert "A=1" in content
    assert "B=22" in content
    assert f"OPENROUTER_MODEL={OPENROUTER_DEFAULTS['OPENROUTER_MODEL']}" in content


def test_openrouter_configured_detects_api_key(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENROUTER_API_KEY=test-key\n", encoding="utf-8")

    assert openrouter_configured(env) is True
