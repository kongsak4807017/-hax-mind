from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.utils import ROOT


@dataclass(frozen=True)
class SetupMode:
    key: str
    slug: str
    title: str
    description: str
    run_tests: bool
    run_secret_audit: bool
    register_tasks: bool
    recommended_start: str


SETUP_MODES: tuple[SetupMode, ...] = (
    SetupMode(
        key="1",
        slug="quick",
        title="Quick local setup",
        description="Create or refresh the local Python environment, install requirements, create .env from template if needed, and run tests.",
        run_tests=True,
        run_secret_audit=False,
        register_tasks=False,
        recommended_start="none",
    ),
    SetupMode(
        key="2",
        slug="bot",
        title="Telegram bot setup",
        description="Quick setup plus secret audit and an easy path to launch the Telegram bot after configuration.",
        run_tests=True,
        run_secret_audit=True,
        register_tasks=False,
        recommended_start="visible-current",
    ),
    SetupMode(
        key="3",
        slug="production",
        title="Local production setup",
        description="Quick setup plus secret audit, scheduled-task registration, and background bot recovery for always-on local use.",
        run_tests=True,
        run_secret_audit=True,
        register_tasks=True,
        recommended_start="background",
    ),
    SetupMode(
        key="4",
        slug="repair",
        title="Repair / re-check current install",
        description="Reinstall dependencies into the existing environment, run tests, audit secrets, and generate a fresh health snapshot.",
        run_tests=True,
        run_secret_audit=True,
        register_tasks=False,
        recommended_start="none",
    ),
)


def get_setup_modes() -> tuple[SetupMode, ...]:
    return SETUP_MODES


def get_setup_mode(selection: str) -> SetupMode:
    normalized = selection.strip().lower()
    for mode in SETUP_MODES:
        if normalized in {mode.key, mode.slug}:
            return mode
    valid = ", ".join(f"{mode.key}/{mode.slug}" for mode in SETUP_MODES)
    raise ValueError(f"Unknown setup mode '{selection}'. Valid values: {valid}")


def format_setup_menu() -> str:
    lines = [
        "",
        "HAX-Mind setup modes",
        "====================",
    ]
    for mode in SETUP_MODES:
        lines.extend(
            [
                f"{mode.key}. {mode.title}",
                f"   {mode.description}",
            ]
        )
    lines.extend(
        [
            "",
            "Choose a setup mode by number:",
        ]
    )
    return "\n".join(lines)


def detect_env_file(project_root: Path = ROOT) -> Path | None:
    for name in (".env", ".env.txt"):
        candidate = project_root / name
        if candidate.exists():
            return candidate
    return None


def ensure_env_file(project_root: Path = ROOT) -> Path | None:
    existing = detect_env_file(project_root)
    if existing:
        return existing
    template = project_root / ".env.example"
    if not template.exists():
        return None
    destination = project_root / ".env"
    destination.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


OPENROUTER_DEFAULTS: dict[str, str] = {
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "OPENROUTER_MODEL": "openrouter/free",
    "OPENROUTER_APP_NAME": "HAX-Mind",
    "OPENROUTER_SITE_URL": "",
}


def read_env_values(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def upsert_env_values(env_path: Path, values: dict[str, str]) -> None:
    existing_lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines() if env_path.exists() else []
    remaining = dict(values)
    updated_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _ = stripped.split("=", 1)
            key = key.strip()
            if key in remaining:
                updated_lines.append(f"{key}={remaining.pop(key)}")
                continue
        updated_lines.append(line)

    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")

    for key, value in remaining.items():
        updated_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")


def openrouter_configured(env_path: Path) -> bool:
    values = read_env_values(env_path)
    return bool(values.get("OPENROUTER_API_KEY", "").strip())
