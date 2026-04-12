from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.setup_wizard import (
    OPENROUTER_DEFAULTS,
    detect_env_file,
    ensure_env_file,
    format_setup_menu,
    get_setup_mode,
    get_setup_modes,
    read_env_values,
    upsert_env_values,
)


ROOT = Path(__file__).resolve().parent.parent


def print_banner() -> None:
    print("")
    print("HAX-Mind Setup")
    print("")
    print(f"Project: {ROOT}")
    print("")


def choose_mode_interactively() -> str:
    print(format_setup_menu())
    while True:
        selection = input("> ").strip()
        if selection:
            try:
                return get_setup_mode(selection).slug
            except ValueError as exc:
                print(exc)


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    reply = input(f"{prompt} {suffix} ").strip().lower()
    if not reply:
        return default
    return reply in {"y", "yes"}


def ask_start_mode(default: str) -> str:
    options = {
        "1": "visible-current",
        "2": "visible-new",
        "3": "background",
        "4": "none",
        "visible-current": "visible-current",
        "visible-new": "visible-new",
        "background": "background",
        "none": "none",
    }
    print("")
    print("Start mode")
    print("==========")
    print("1. Visible in this setup window")
    print("   - run-all.bat takes over this terminal and keeps the bot in the foreground")
    print("2. Visible in a new terminal window")
    print("   - setup finishes, then opens a separate HAX-Mind terminal window")
    print("3. Background / supervised")
    print("   - uses run-recover.cmd and returns immediately")
    print("4. Don't start now")
    while True:
        selection = input(f"Choose start mode [{default}]: ").strip().lower()
        if not selection:
            return default
        if selection in options:
            return options[selection]
        print("Please choose 1, 2, 3, 4, visible-current, visible-new, background, or none.")


def configure_openrouter(env_path: Path, *, force_prompt: bool = False) -> bool:
    existing = read_env_values(env_path)
    already_configured = bool(existing.get("OPENROUTER_API_KEY", "").strip())
    if already_configured and not force_prompt:
        print(f"[ok] OpenRouter already configured in {env_path.name}")
        return False

    print("")
    print("OpenRouter configuration")
    print("=======================")
    print("This wizard can save an OpenRouter setup for future HAX-Mind orchestration.")
    print("Recommended free-router model default: openrouter/free")

    api_key = getpass.getpass("OpenRouter API key: ").strip()
    if not api_key:
        print("[warn] No OpenRouter API key entered. Skipping OpenRouter setup.")
        return False

    default_model = existing.get("OPENROUTER_MODEL", OPENROUTER_DEFAULTS["OPENROUTER_MODEL"]) or OPENROUTER_DEFAULTS["OPENROUTER_MODEL"]
    model = input(f"OpenRouter model [{default_model}]: ").strip() or default_model

    default_app_name = existing.get("OPENROUTER_APP_NAME", OPENROUTER_DEFAULTS["OPENROUTER_APP_NAME"]) or OPENROUTER_DEFAULTS["OPENROUTER_APP_NAME"]
    app_name = input(f"App name sent to OpenRouter [{default_app_name}]: ").strip() or default_app_name

    default_site_url = existing.get("OPENROUTER_SITE_URL", OPENROUTER_DEFAULTS["OPENROUTER_SITE_URL"])
    site_url = input(f"Site URL header for OpenRouter [{default_site_url or 'blank'}]: ").strip()
    if not site_url:
        site_url = default_site_url

    values = {
        "OPENROUTER_API_KEY": api_key,
        "OPENROUTER_BASE_URL": OPENROUTER_DEFAULTS["OPENROUTER_BASE_URL"],
        "OPENROUTER_MODEL": model,
        "OPENROUTER_APP_NAME": app_name,
        "OPENROUTER_SITE_URL": site_url,
    }
    upsert_env_values(env_path, values)
    print(f"[ok] Saved OpenRouter configuration to {env_path.name}")
    return True


def run_command(command: list[str], *, description: str, env: dict[str, str] | None = None) -> None:
    print(f"[step] {description}")
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def ensure_virtualenv() -> Path:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        print(f"[ok] Virtual environment already exists: {venv_python}")
        return venv_python
    run_command([sys.executable, "-m", "venv", str(ROOT / ".venv")], description="Creating .venv")
    if not venv_python.exists():
        raise RuntimeError("Virtual environment creation finished but .venv\\Scripts\\python.exe was not found.")
    print(f"[ok] Virtual environment created: {venv_python}")
    return venv_python


def install_requirements(venv_python: Path) -> None:
    run_command([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], description="Upgrading pip")
    run_command([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], description="Installing requirements")
    print("[ok] Requirements installed")


def maybe_create_env_file() -> Path | None:
    existing = detect_env_file(ROOT)
    if existing:
        print(f"[ok] Env file already exists: {existing.name}")
        return existing
    created = ensure_env_file(ROOT)
    if created:
        print(f"[ok] Created {created.name} from .env.example")
    else:
        print("[warn] No .env.example found, so no env file was created.")
    return created


def maybe_open_env(env_path: Path | None, *, yes: bool) -> None:
    if env_path is None:
        return
    if yes or ask_yes_no(f"Open {env_path.name} in Notepad so you can fill in your secrets now?"):
        subprocess.Popen(["notepad.exe", str(env_path)], cwd=ROOT)


def run_tests(venv_python: Path) -> None:
    run_command([str(venv_python), "-m", "pytest", "tests"], description="Running tests")
    print("[ok] Tests passed")


def run_secret_audit(venv_python: Path) -> None:
    run_command([str(venv_python), "-c", "from engine.secret_ops import audit_secret_status; audit_secret_status()"], description="Auditing secret status")
    print("[ok] Secret audit completed (see runtime/reports/secret_status.json)")


def register_tasks() -> None:
    run_command(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "register-scheduled-tasks.ps1")],
        description="Registering scheduled tasks",
    )
    print("[ok] Scheduled tasks registered (or Startup fallback installed)")


def run_health() -> None:
    run_command(["cmd.exe", "/c", "run-health.cmd"], description="Running health snapshot")
    print("[ok] Health snapshot completed")


def start_haxmind(start_mode: str) -> None:
    if start_mode == "visible-current":
        print("")
        print("Launching HAX-Mind in a visible terminal window...")
        print("Keep the window open while the bot is running.")
        subprocess.run(["cmd.exe", "/c", "run-all.bat"], cwd=ROOT, check=True)
        return
    if start_mode == "visible-new":
        print("[step] Launching HAX-Mind in a new terminal window")
        subprocess.Popen(["cmd.exe", "/c", "start", "\"HAX-Mind\"", "cmd.exe", "/k", "run-all.bat"], cwd=ROOT)
        print("[ok] New HAX-Mind terminal window requested")
        return
    if start_mode == "background":
        run_command(["cmd.exe", "/c", "run-recover.cmd"], description="Starting HAX-Mind in background mode")
        print("[ok] Background bot recovery/start completed")
        return
    print("[ok] Setup finished without starting the bot")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guided setup for HAX-Mind on Windows")
    parser.add_argument("--mode", choices=[mode.slug for mode in get_setup_modes()], help="Setup mode to run non-interactively")
    parser.add_argument("--yes", action="store_true", help="Accept the recommended prompts automatically")
    parser.add_argument("--start", choices=["visible-current", "visible-new", "background", "none"], help="Override the final start behavior")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest during setup")
    parser.add_argument("--skip-open-env", action="store_true", help="Don't offer to open .env in Notepad")
    parser.add_argument("--configure-openrouter", action="store_true", help="Prompt for OpenRouter API key and model during setup")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    print_banner()
    mode_slug = args.mode or choose_mode_interactively()
    mode = get_setup_mode(mode_slug)
    start_mode = args.start or mode.recommended_start

    if not args.mode:
        print("")
        print(f"Selected: {mode.title}")
        print(mode.description)
        if args.start is None:
            start_mode = ask_start_mode(mode.recommended_start)
        if not args.skip_tests and mode.run_tests and not args.yes:
            if not ask_yes_no("Run pytest after installation?", default=True):
                args.skip_tests = True
        if not args.configure_openrouter:
            args.configure_openrouter = ask_yes_no("Configure OpenRouter (API key + model) now?", default=False)

    venv_python = ensure_virtualenv()
    install_requirements(venv_python)
    env_path = maybe_create_env_file()

    if mode.run_secret_audit:
        run_secret_audit(venv_python)

    if env_path and not args.skip_open_env:
        maybe_open_env(env_path, yes=args.yes and mode.slug in {"bot", "production"})

    if env_path and args.configure_openrouter:
        configure_openrouter(env_path, force_prompt=args.configure_openrouter)

    if mode.register_tasks:
        register_tasks()

    if mode.run_tests and not args.skip_tests:
        run_tests(venv_python)

    run_health()

    print("")
    print("Next steps")
    print("==========")
    print("1. Put your real secrets into .env or .env.txt if you haven't done that yet.")
    print("2. Talk to your Telegram bot with /start, /status, and /health.")
    print("3. Use run-all.bat for a visible session or run-recover.cmd for background mode.")
    if env_path:
        env_values = read_env_values(env_path)
        if env_values.get("OPENROUTER_API_KEY", "").strip():
            print(f"4. OpenRouter ready with model: {env_values.get('OPENROUTER_MODEL', OPENROUTER_DEFAULTS['OPENROUTER_MODEL'])}")

    if mode.slug in {"bot", "production"} or start_mode != "none":
        start_haxmind(start_mode)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from exc
    except KeyboardInterrupt:
        raise SystemExit(130)
