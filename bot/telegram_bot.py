from __future__ import annotations

import asyncio
import ctypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from engine.auth import auth_status_for_user, is_authorized_user
from engine.github_ingestor import ingest_all_tools
from engine.dreaming import explain_dream, get_dream, latest_dream, memory_status, remember_text, run_dream_cycle
from engine.dream_tasks import create_task_from_dream
from engine.local_health import render_local_health_summary
from engine.memory_analyzer import log_event, summarize_today
from engine.memory_intelligence import cluster_topics, hybrid_recall, list_decisions, run_phase3_cycle
from engine.morning_report import generate_morning_report
from engine.mission_engine import (
    create_execution_proposal_from_mission,
    create_mission,
    get_mission,
    list_missions,
    update_mission_status,
)
from engine.picoclaw_manager import list_remote_jobs, picoclaw_plan, picoclaw_status, queue_proposal_for_remote_safe_execution, worker_status
from engine.proposal_engine import list_proposals, update_proposal_status
from engine.apply_engine import execute_proposal_safe
from engine.auto_learning import (
    handle_unknown_question,
    nightly_learning_cycle,
    get_learning_status,
    render_learning_summary,
    trigger_immediate_learning,
)
from engine.cli_bridge import (
    approve_cli_session,
    close_cli_session,
    create_cli_improvement_proposal,
    continue_cli_session,
    get_cli_job,
    get_cli_output,
    get_cli_session,
    latest_cli_session,
    latest_cli_job,
    open_cli_session,
    render_cli_job_detail,
    render_cli_jobs_summary,
    render_cli_session_detail,
    render_cli_sessions_summary,
    set_cli_session_profile,
    start_cli_session,
    render_cli_tools_summary,
    run_cli_once,
)
from engine.project_manager import list_projects, register_project
from engine.repo_analyzer import analyze_github_repo_and_dream
from engine.research_engine import (
    approve_research_proposal,
    ResearchError,
    close_research_session,
    continue_research_session,
    create_proposal_from_research,
    create_task_from_research,
    get_research,
    get_research_session,
    latest_research,
    latest_research_session,
    list_research_sessions,
    render_research_artifact,
    render_research_output,
    render_research_reply,
    render_research_session_detail,
    render_research_sessions_summary,
    run_research,
    start_research_session,
)
from engine.restart_manager import request_bot_restart
from engine.research_team import generate_team_brief
from engine.rollback_engine import rollback_proposal
from engine.confirmation_store import (
    clear_pending_confirmation,
    get_pending_confirmation,
    interpret_confirmation_reply,
    save_pending_confirmation,
)
from engine.conversation_memory import append_conversation_turn, get_recent_context
from engine.orchestrator import OrchestrationPlan, execute_orchestration_plan, looks_like_plain_text_request, route_message_to_plan
from engine.openrouter_client import OpenRouterError
from engine.self_improvement_engine import generate_improvement_proposal
from engine.team_orchestrator import create_team_plan, get_team_plan, list_team_plans
from engine.tool_registry import iter_tools
from engine.utils import ROOT, ensure_dir, now_iso, read_env_file

read_env_file()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PID_PATH = ROOT / "runtime" / "telegram_bot.pid"
BOT_LOG_PATH = ROOT / "runtime" / "logs" / "telegram_bot.lifecycle.log"
BOT_ERR_LOG_PATH = ROOT / "runtime" / "logs" / "telegram_bot.err.log"
_BOT_MUTEX_NAME = "Local\\HAXMindTelegramBotSingleton"
_ERROR_ALREADY_EXISTS = 183


class BotInstanceLock:
    def __init__(self) -> None:
        self._handle = None

    def acquire(self) -> None:
        if os.name != "nt":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, _BOT_MUTEX_NAME)
        if not handle:
            raise RuntimeError("Unable to create Windows mutex for HAX-Mind bot")
        last_error = ctypes.get_last_error()
        if last_error == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            raise RuntimeError("Another HAX-Mind Telegram bot instance is already running.")
        self._handle = handle

    def release(self) -> None:
        if os.name != "nt" or not self._handle:
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(self._handle)
        self._handle = None


def _chunk_text(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks near newlines, falling back to hard split."""
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = max_len
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    return [c for c in chunks if c]


async def send_long_text(message, text: str, parse_mode=None) -> None:
    """Send long text as multiple messages."""
    for chunk in _chunk_text(text):
        await message.reply_text(chunk, parse_mode=parse_mode)


async def edit_or_reply_long_text(message, text: str, parse_mode=None) -> None:
    """Edit a message with the first chunk, then reply with remaining chunks."""
    chunks = _chunk_text(text)
    if not chunks:
        return
    await message.edit_text(chunks[0], parse_mode=parse_mode)
    for chunk in chunks[1:]:
        await message.reply_text(chunk, parse_mode=parse_mode)


def _read_cli_output(job: dict) -> str:
    """Read full CLI output from file if available, else stdout_excerpt."""
    path = job.get("output_path")
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            pass
    return job.get("stdout_excerpt", "")


def _user_id(update: Update) -> int | None:
    return update.effective_user.id if update.effective_user else None


async def _guard(update: Update) -> bool:
    if is_authorized_user(_user_id(update)):
        return True
    if update.message:
        await update.message.reply_text("Unauthorized Telegram user. Ask the owner to add your user ID to TELEGRAM_ALLOWED_USER_IDS.")
    return False


def require_auth(handler):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await _guard(update):
            return
        await handler(update, context)

    return wrapped


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        await update.message.reply_text("No Telegram user found on this update.")
        return
    await update.message.reply_text(f"Your Telegram user id: {user.id}\nUsername: @{user.username or '-'}")


async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status = auth_status_for_user(_user_id(update))
    await update.message.reply_text(
        "\n".join(
            [
                f"Allowlist enabled: {status.allowlist_enabled}",
                f"Allowed users configured: {status.allowed_count}",
                f"Your user id: {status.user_id}",
                f"You are authorized: {status.authorized}",
            ]
        )
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "HAX-Mind ready. Commands: /whoami /auth /status /restart /research <query>|latest|output [research_id|latest]|artifact [research_id|latest]|sessions|session <id|latest>|start <query>|continue <session_id|latest> <query>|close <session_id|latest>|task <project_id> [research_id|latest]|propose [research_id|latest]|approve [research_id|latest] /project add|list /task <project> <work> /tasks /taskstatus <id> /propose <task_id> /approve <proposal_id> /execute <proposal_id> /picoclaw status|worker status|plan|jobs|queue <approved_proposal_id> /cli tools|jobs|sessions|session <id|latest>|latest|output [job_id|latest]|status <job_id>|start <tool> [profile] <prompt>|continue <session_id|latest> <prompt>|mode <session_id|latest> <profile>|approve <session_id|latest>|diff|close <session_id|latest>|open <tool> <prompt>|run <tool> <prompt>|improve /memory /recall <query> /phase3 now /clusters /decisions /team <topic> | /team plan|list|status <task_id> /dream now|latest|explain [dream_id|latest]|task <project_id> [dream_id|latest] /analyze repo <url> /report\nStructured task syntax for guarded real apply: /task <project_id> append|replace|create|delete <path> :: <content>"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(render_local_health_summary())


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await status(update, context)


async def tools(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = [f"{tool.id} | {tool.role} | phase {tool.integration_phase}" for tool in iter_tools()]
    await update.message.reply_text("\n".join(lines))


async def project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or context.args[0].lower() == "list":
        projects = list_projects()
        if not projects:
            await update.message.reply_text("No projects registered. Usage: /project add <name> <path_or_repo>")
            return
        await update.message.reply_text("\n".join(f"{p['id']} | {p['name']} | {p['path_or_repo']}" for p in projects[:10]))
        return
    if context.args[0].lower() != "add" or len(context.args) < 3:
        await update.message.reply_text("Usage: /project add <name> <path_or_repo> OR /project list")
        return
    item = register_project(context.args[1], " ".join(context.args[2:]))
    await update.message.reply_text(f"Project registered: {item['id']} -> {item['path_or_repo']}")


async def task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /task <project_id> <work description>")
        return
    try:
        mission = create_mission(context.args[0], " ".join(context.args[1:]))
    except Exception as exc:
        await update.message.reply_text(f"Task creation failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"Task created: {mission['id']}",
                f"Project: {mission['project_name']}",
                f"Status: {mission['status']}",
                f"Plan: runtime/task_plans/{mission['id']}.md",
            ]
        )
    )


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    missions = list_missions()
    if not missions:
        await update.message.reply_text("No tasks yet.")
        return
    await send_long_text(update.message, "\n".join(f"{m['id']} | {m['project_name']} | {m['status']} | {m['description']}" for m in missions))


async def taskdone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /taskdone <task_id>")
        return
    try:
        mission = update_mission_status(context.args[0], "done")
    except Exception as exc:
        await update.message.reply_text(f"Task update failed: {exc}")
        return
    await update.message.reply_text(f"Task marked done: {mission['id']}")


async def picoclaw(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    action = context.args[0].lower() if context.args else "status"
    if action == "worker":
        subaction = context.args[1].lower() if len(context.args) > 1 else "status"
        if subaction != "status":
            await update.message.reply_text("Usage: /picoclaw worker status")
            return
        state = worker_status()
        await update.message.reply_text(
            "\n".join(
                [
                    f"PicoClaw worker status: {state['status']}",
                    f"Worker: {state['worker_id'] or 'none'}",
                    f"Last seen: {state['last_seen_at'] or 'never'}",
                    f"Capabilities: {', '.join(state.get('capabilities', [])) or 'none'}",
                    state["summary"],
                ]
            )
        )
        return
    if action == "status":
        state = picoclaw_status()
        ready = state["readiness"]
        done = sum(1 for value in ready.values() if value)
        total = len(ready)
        queue = state.get("queue_counts", {})
        heartbeat = state.get("latest_heartbeat")
        await update.message.reply_text(
            "\n".join(
                [
                    f"PicoClaw: {state['status']} (Phase {state['phase']})",
                    f"Readiness: {done}/{total}",
                    f"Secret configured: {ready['worker_auth_secret_configured']}",
                    f"Remote queue: pending={queue.get('pending', 0)} claimed={queue.get('claimed', 0)} completed={queue.get('completed', 0)} failed={queue.get('failed', 0)}",
                    f"Latest heartbeat: {heartbeat['worker_id']} @ {heartbeat['last_seen_at']}" if heartbeat else "Latest heartbeat: none yet",
                    "Use /picoclaw worker status, /picoclaw plan, /picoclaw jobs, or /picoclaw queue <approved_proposal_id>.",
                ]
            )
        )
        return
    if action == "plan":
        picoclaw_plan()
        await update.message.reply_text(
            "PicoClaw Phase 2 plan saved: docs/picoclaw-phase2.md\nShort answer: the local control plane is ready now; set the shared secret, record a worker heartbeat, then queue approved safe-check jobs."
        )
        return
    if action == "jobs":
        jobs = list_remote_jobs(limit=5)
        if not jobs:
            await update.message.reply_text("No PicoClaw remote jobs yet.")
            return
        await update.message.reply_text(
            "\n".join(
                f"{job['id']} | {job['status']} | {job['job_type']} | by {job['created_by']}"
                for job in jobs
            )
        )
        return
    if action == "queue":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /picoclaw queue <approved_proposal_id>")
            return
        try:
            job = queue_proposal_for_remote_safe_execution(context.args[1], created_by="telegram")
        except Exception as exc:
            await update.message.reply_text(f"PicoClaw queue failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Queued remote job: {job['id']}",
                    f"Type: {job['job_type']}",
                    f"Proposal: {job['payload']['proposal_id']}",
                    f"Mode: {job['mode']}",
                ]
            )
        )
        return
    await update.message.reply_text("Usage: /picoclaw status | worker status | plan | jobs | queue <approved_proposal_id>")


async def cli(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_args = list(context.args)
    action = raw_args[0].lower() if raw_args else "tools"
    tool_keys = {"codex", "omx", "gemini", "kimi"}
    if action == "tool":
        action = "tools"
    if action in tool_keys:
        if action in {"kimi", "gemini", "codex", "omx"}:
            raw_args = ["start", *raw_args]
            action = "start"
        else:
            raw_args = ["open", *raw_args]
            action = "open"
    elif action in {"เปิด", "open"} and len(raw_args) >= 2 and raw_args[1].lower() in tool_keys:
        if raw_args[1].lower() in {"kimi", "gemini", "codex", "omx"}:
            raw_args = ["start", *raw_args[1:]]
            action = "start"
        else:
            action = "open"
    elif action in {"รัน", "run"} and len(raw_args) >= 2 and raw_args[1].lower() in tool_keys:
        action = "run"
    elif action in {"latest", "proof", "หลักฐาน"}:
        action = "latest"
    if action == "tools":
        await update.message.reply_text(render_cli_tools_summary())
        return
    if action == "jobs":
        await update.message.reply_text(render_cli_jobs_summary())
        return
    if action == "sessions":
        await update.message.reply_text(render_cli_sessions_summary())
        return
    if action == "latest":
        session = latest_cli_session()
        if session:
            parts = [render_cli_session_detail(session)]
            last_job_id = session.get("last_job_id")
            if last_job_id:
                try:
                    parts.append("")
                    parts.append(render_cli_job_detail(get_cli_job(last_job_id)))
                except Exception:
                    pass
            await send_long_text(update.message, "\n".join(parts))
            return
        job = latest_cli_job()
        if not job:
            await update.message.reply_text("No CLI jobs yet.")
            return
        await send_long_text(update.message, render_cli_job_detail(job))
        return
    if action == "session":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            session = latest_cli_session() if ref == "latest" else get_cli_session(ref)
        except Exception as exc:
            await update.message.reply_text(f"CLI session lookup failed: {exc}")
            return
        if not session:
            await update.message.reply_text("No CLI session yet.")
            return
        await send_long_text(update.message, render_cli_session_detail(session))
        return
    if action == "mode":
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /cli mode <session_id|latest> <profile>")
            return
        try:
            session = set_cli_session_profile(raw_args[1], raw_args[2])
        except Exception as exc:
            await update.message.reply_text(f"CLI mode change failed: {exc}")
            return
        await send_long_text(update.message, render_cli_session_detail(session))
        return
    if action == "approve":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            session = approve_cli_session(ref)
        except Exception as exc:
            await update.message.reply_text(f"CLI approve failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Approved CLI session: {session['id']}",
                    f"Tool: {session['tool']}",
                    f"Profile: {session.get('profile', 'default')}",
                    "Use /cli continue latest <prompt> for the next step.",
                ]
            )
        )
        return
    if action == "diff":
        job = latest_cli_job()
        if not job:
            await update.message.reply_text("No CLI jobs yet.")
            return
        diff = job.get("diff_excerpt")
        if not diff:
            await update.message.reply_text("No diff captured for the latest CLI job.")
            return
        await send_long_text(update.message, f"Latest CLI diff:\n{diff}")
        return
    if action == "start":
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /cli start <kimi|gemini|codex|omx> [profile] <prompt>")
            return
        tool = raw_args[1].lower()
        profile = None
        prompt_index = 2
        profile_map = {
            "kimi": {"default", "thinking", "yolo"},
            "gemini": {"default", "plan", "yolo"},
            "codex": {"review", "default", "yolo"},
            "omx": {"review", "default", "yolo"},
        }
        if tool in profile_map and len(raw_args) >= 4 and raw_args[2].lower() in profile_map[tool]:
            profile = raw_args[2].lower()
            prompt_index = 3
        if len(raw_args) <= prompt_index:
            await update.message.reply_text("Usage: /cli start <kimi|gemini|codex|omx> [profile] <prompt>")
            return
        
        prompt_text = " ".join(raw_args[prompt_index:])
        
        # Step 1: Acknowledge command
        status_msg = await update.message.reply_text(
            f"[1/4] รับคำสั่งแล้ว\n"
            f"Tool: {tool}\n"
            f"Profile: {profile or 'default'}\n"
            f"กำลังตรวจสอบ CLI tool..."
        )
        
        try:
            # Step 2: Validate tool availability
            from engine.cli_bridge import _available_tool_or_raise
            try:
                tool_obj = _available_tool_or_raise(tool)
                await status_msg.edit_text(
                    f"[2/4] พบ CLI tool: {tool_obj.title}\n"
                    f"Path: {tool_obj.executable}\n"
                    f"กำลังสร้าง session..."
                )
            except FileNotFoundError as e:
                await status_msg.edit_text(f"[ERROR] ไม่พบ CLI tool: {e}")
                return
            
            # Step 3: Create session
            await status_msg.edit_text(
                f"[2/4] พบ CLI tool: {tool}\n"
                f"[3/4] กำลังสร้าง session และสั่งให้ CLI ทำงาน...\n"
                f"Prompt: {prompt_text[:100]}..."
            )
            
            session, job = start_cli_session(tool, prompt_text, profile=profile)
            
            # Step 4: Report completion
            job_status = job.get('status', 'unknown')
            exit_code = job.get('exit_code', 'N/A')
            
            result_lines = [
                f"[4/4] เสร็จสิ้น!",
                f"",
                f"Session: {session['id']}",
                f"Tool: {session['tool']}",
                f"Profile: {session.get('profile', 'default')}",
                f"Job: {job['id']}",
                f"Status: {job_status}",
            ]
            if exit_code != 'N/A':
                result_lines.append(f"Exit code: {exit_code}")
            stdout_text = _read_cli_output(job)
            if stdout_text:
                result_lines.append(f"")
                result_lines.append(f"Output preview:")
                result_lines.append(f"```")
                result_lines.append(stdout_text)
                result_lines.append(f"```")
            
            result_lines.append(f"")
            result_lines.append(f"Use /cli continue latest <prompt> for next step")
            
            await edit_or_reply_long_text(status_msg, "\n".join(result_lines), parse_mode="Markdown")
            
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            await edit_or_reply_long_text(
                status_msg,
                f"[ERROR] CLI session start failed:\n"
                f"{exc}\n\n"
                f"รายละเอียด:\n"
                f"```\n{error_detail}\n```",
                parse_mode="Markdown"
            )
            return
        return
    if action == "continue":
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /cli continue <session_id|latest> <prompt>")
            return
        
        session_ref = raw_args[1]
        prompt_text = " ".join(raw_args[2:])
        
        # Step 1: Acknowledge
        status_msg = await update.message.reply_text(
            f"[1/3] รับคำสั่ง continue session\n"
            f"Session: {session_ref}\n"
            f"กำลังค้นหา session..."
        )
        
        try:
            # Step 2: Get session info
            from engine.cli_bridge import get_cli_session, latest_cli_session
            session = latest_cli_session() if session_ref == "latest" else get_cli_session(session_ref)
            if not session:
                await status_msg.edit_text(f"[ERROR] ไม่พบ session: {session_ref}")
                return
            
            await status_msg.edit_text(
                f"[2/3] พบ session: {session['id']}\n"
                f"Tool: {session['tool']}\n"
                f"Step ก่อนหน้า: {session.get('step_count', 0)}\n"
                f"กำลังส่ง prompt ให้ CLI..."
            )
            
            # Step 3: Continue session
            job = continue_cli_session(session_ref, prompt_text)
            
            # Report result
            job_status = job.get('status', 'unknown')
            
            result_lines = [
                f"[3/3] เสร็จสิ้น!",
                f"",
                f"Job: {job['id']}",
                f"Session: {job.get('session_id', 'N/A')}",
                f"Status: {job_status}",
            ]
            stdout_text = _read_cli_output(job)
            if stdout_text:
                result_lines.append(f"")
                result_lines.append(f"Output:")
                result_lines.append(f"```")
                result_lines.append(stdout_text)
                result_lines.append(f"```")
            
            result_lines.append(f"")
            result_lines.append(f"Use /cli continue latest <prompt> for next step")
            
            await edit_or_reply_long_text(status_msg, "\n".join(result_lines), parse_mode="Markdown")
            
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            await edit_or_reply_long_text(
                status_msg,
                f"[ERROR] CLI continue failed:\n"
                f"{exc}\n\n"
                f"รายละเอียด:\n"
                f"```\n{error_detail}\n```",
                parse_mode="Markdown"
            )
            return
        return
    if action == "close":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            session = close_cli_session(ref)
        except Exception as exc:
            await update.message.reply_text(f"CLI close failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Closed CLI session: {session['id']}",
                    f"Tool: {session['tool']}",
                    f"Steps: {session.get('step_count', 0)}",
                ]
            )
        )
        return
    if action == "status":
        if len(raw_args) < 2:
            await update.message.reply_text("Usage: /cli status <job_id>")
            return
        try:
            job = get_cli_job(raw_args[1])
        except Exception as exc:
            await update.message.reply_text(f"CLI job lookup failed: {exc}")
            return
        await send_long_text(update.message, render_cli_job_detail(job))
        return
    if action == "output":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            job = latest_cli_job() if ref == "latest" else get_cli_job(ref)
            if not job:
                await update.message.reply_text("No CLI job found.")
                return
            output = get_cli_output(job['id'])
            await update.message.reply_text(f"Output for {job['id']}:")
            await send_long_text(update.message, f"```\n{output}\n```")
        except Exception as exc:
            await update.message.reply_text(f"CLI output fetch failed: {exc}")
        return
    if action == "open":
        if len(raw_args) >= 2 and raw_args[0].lower() in {"เปิด", "open"}:
            raw_args = ["open", *raw_args[1:]]
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /cli open <codex|omx|gemini|kimi> <prompt>")
            return
        
        tool = raw_args[1].lower()
        prompt_text = " ".join(raw_args[2:])
        
        # Step 1: Acknowledge command
        status_msg = await update.message.reply_text(
            f"[1/4] รับคำสั่งเปิด CLI (Interactive Mode)\n"
            f"Tool: {tool}\n"
            f"กำลังตรวจสอบ CLI tool..."
        )
        
        try:
            # Step 2: Validate tool
            from engine.cli_bridge import _available_tool_or_raise
            try:
                tool_obj = _available_tool_or_raise(tool)
                await status_msg.edit_text(
                    f"[2/4] พบ CLI tool: {tool_obj.title}\n"
                    f"Path: {tool_obj.executable}\n"
                    f"กำลังสร้าง job และ launcher..."
                )
            except FileNotFoundError as e:
                await status_msg.edit_text(f"[ERROR] ไม่พบ CLI tool: {e}")
                return
            
            # Step 3: Open CLI session
            await status_msg.edit_text(
                f"[2/4] พบ CLI tool: {tool}\n"
                f"[3/4] กำลังสร้าง launcher และเปิดหน้าต่าง CLI...\n"
                f"Prompt: {prompt_text[:100]}..."
            )
            
            job = open_cli_session(tool, prompt_text)
            
            # Step 4: Wait and get initial output
            await status_msg.edit_text(
                f"[3/4] เปิด CLI window แล้ว\n"
                f"Job ID: {job['id']}\n"
                f"[4/4] รอ CLI เริ่มต้น (3 วินาที)..."
            )
            
            import asyncio
            await asyncio.sleep(3)
            
            initial_output = get_cli_output(job['id'])
            
            result_lines = [
                f"[4/4] เสร็จสิ้น! CLI window เปิดแล้ว",
                f"",
                f"Job: {job['id']}",
                f"Tool: {job['tool']}",
                f"Status: {job['status']}",
                f"Output file: {job.get('output_path', 'N/A')}",
                f"",
                f"Initial output preview:",
                f"```",
            ]
            
            if initial_output and initial_output != "Output file not yet created. CLI may still be starting up.":
                result_lines.append(initial_output)
            else:
                result_lines.append("(CLI ยังเริ่มต้น หรือยังไม่มี output)")
            
            result_lines.append(f"```")
            result_lines.append(f"")
            result_lines.append(f"Window เปิดอยู่บน desktop ของคุณ")
            result_lines.append(f"ใช้ `/cli output` เพื่อดึง output ล่าสุด")
            
            await edit_or_reply_long_text(status_msg, "\n".join(result_lines), parse_mode="Markdown")
            
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            await edit_or_reply_long_text(
                status_msg,
                f"[ERROR] CLI open failed:\n"
                f"{exc}\n\n"
                f"รายละเอียด:\n"
                f"```\n{error_detail}\n```",
                parse_mode="Markdown"
            )
            return
        return
    if action == "run":
        if len(raw_args) >= 2 and raw_args[0].lower() in {"รัน", "run"}:
            raw_args = ["run", *raw_args[1:]]
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /cli run <codex|omx|gemini|kimi> <prompt>")
            return
        
        tool = raw_args[1].lower()
        prompt_text = " ".join(raw_args[2:])
        
        # Step 1: Acknowledge
        status_msg = await update.message.reply_text(
            f"[1/4] รับคำสั่งรัน CLI (One-shot Mode)\n"
            f"Tool: {tool}\n"
            f"กำลังตรวจสอบ CLI tool..."
        )
        
        try:
            # Step 2: Validate
            from engine.cli_bridge import _available_tool_or_raise
            try:
                tool_obj = _available_tool_or_raise(tool)
                await status_msg.edit_text(
                    f"[2/4] พบ CLI tool: {tool_obj.title}\n"
                    f"กำลังรัน (อาจใช้เวลาสักครู่)..."
                )
            except FileNotFoundError as e:
                await status_msg.edit_text(f"[ERROR] ไม่พบ CLI tool: {e}")
                return
            
            # Step 3: Run CLI
            await status_msg.edit_text(
                f"[2/4] พบ CLI tool: {tool}\n"
                f"[3/4] กำลังประมวลผล...\n"
                f"⏳ รอ CLI ตอบกลับ (timeout 3 นาที)"
            )
            
            job = run_cli_once(tool, prompt_text)
            
            # Step 4: Report result
            job_status = job.get('status', 'unknown')
            exit_code = job.get('exit_code', 'N/A')
            
            result_lines = [
                f"[4/4] เสร็จสิ้น!",
                f"",
                f"Job: {job['id']}",
                f"Tool: {job['tool']}",
                f"Status: {job_status}",
            ]
            if exit_code != 'N/A':
                result_lines.append(f"Exit code: {exit_code}")
            stdout_text = _read_cli_output(job)
            if stdout_text:
                result_lines.append(f"")
                result_lines.append(f"Output:")
                result_lines.append(f"```")
                result_lines.append(stdout_text)
                result_lines.append(f"```")
            stderr_text = job.get('stderr_excerpt', '')
            if stderr_text:
                result_lines.append(f"")
                result_lines.append(f"Stderr:")
                result_lines.append(f"```")
                result_lines.append(stderr_text)
                result_lines.append(f"```")
            
            await edit_or_reply_long_text(status_msg, "\n".join(result_lines), parse_mode="Markdown")
            
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            await edit_or_reply_long_text(
                status_msg,
                f"[ERROR] CLI run failed:\n"
                f"{exc}\n\n"
                f"รายละเอียด:\n"
                f"```\n{error_detail}\n```",
                parse_mode="Markdown"
            )
            return
        return
    if action == "improve":
        proposal = create_cli_improvement_proposal()
        await update.message.reply_text(
            "\n".join(
                [
                    f"CLI improvement proposal created: {proposal['id']}",
                    f"Risk: {proposal['risk']}",
                    f"Title: {proposal['title']}",
                ]
            )
        )
        return
    await update.message.reply_text("Usage: /cli tools | jobs | sessions | session <id|latest> | latest | output [job_id|latest] | status <job_id> | start <tool> [profile] <prompt> | continue <session_id|latest> <prompt> | mode <session_id|latest> <profile> | approve <session_id|latest> | diff | close <session_id|latest> | open <tool> <prompt> | run <tool> <prompt> | improve\nShort forms: /cli kimi <prompt>, /cli gemini <prompt>, /cli codex <prompt>, /cli omx <prompt>, /cli เปิด kimi <prompt>, /cli รัน gemini <prompt>")


async def learning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-learning system commands"""
    raw_args = list(context.args)
    action = raw_args[0].lower() if raw_args else "status"
    
    if action == "status":
        summary = render_learning_summary()
        await update.message.reply_text(summary)
        return
    
    if action == "queue":
        from engine.auto_learning import get_pending_gaps
        gaps = get_pending_gaps(limit=10)
        if not gaps:
            await update.message.reply_text("No pending knowledge gaps.")
            return
        lines = ["Pending Knowledge Gaps:", ""]
        for gap in gaps:
            status_emoji = "!!" if gap.get("is_important") else "--"
            lines.append(
                f"{status_emoji} {gap['id']}\n"
                f"   Q: {gap['question']}\n"
                f"   Count: {gap.get('recurring_count', 1)} | "
                f"Important: {gap.get('is_important', False)}"
            )
        await send_long_text(update.message, "\n".join(lines))
        return
    
    if action == "topics":
        from engine.auto_learning import get_recurring_topics
        topics = get_recurring_topics(min_count=2)
        if not topics:
            await update.message.reply_text("No recurring topics detected yet.")
            return
        lines = ["Recurring Topics:", ""]
        for topic in topics:
            lines.append(f"- {topic['topic']}: {topic['count']} times")
        await update.message.reply_text("\n".join(lines))
        return
    
    if action == "now":
        await update.message.reply_text("Starting nightly learning cycle...")
        try:
            result = await asyncio.to_thread(nightly_learning_cycle)
            lines = [
                "Learning cycle complete!",
                "",
                f"Recurring topics found: {len(result['recurring_topics'])}",
                f"Important gaps: {result['important_gaps_count']}",
                f"Proposals created: {len(result['proposals_created'])}",
            ]
            if result['proposals_created']:
                lines.append("")
                lines.append("New proposals:")
                for p in result['proposals_created']:
                    lines.append(f"- {p.get('proposal_id', 'unknown')}")
            if result['errors']:
                lines.append("")
                lines.append(f"Errors: {len(result['errors'])}")
            await update.message.reply_text("\n".join(lines))
        except Exception as exc:
            await update.message.reply_text(f"Learning cycle failed: {exc}")
        return
    
    if action == "learn":
        if len(raw_args) < 2:
            await update.message.reply_text("Usage: /learning learn <topic/question>")
            return
        topic = " ".join(raw_args[1:])
        await update.message.reply_text(f"Triggering immediate learning for: {topic}...")
        try:
            result = await asyncio.to_thread(trigger_immediate_learning, topic)
            if result.get("status") == "success":
                await update.message.reply_text(
                    f"Learning complete!\n"
                    f"Proposal: {result.get('proposal_id')}\n"
                    f"Title: {result.get('proposal_title')}\n\n"
                    f"Use `/approve {result.get('proposal_id')}` to review."
                )
            else:
                await update.message.reply_text(
                    f"Learning failed at stage: {result.get('stage', 'unknown')}\n"
                    f"Error: {result.get('error', 'Unknown error')}"
                )
        except Exception as exc:
            await update.message.reply_text(f"Learning error: {exc}")
        return
    
    await update.message.reply_text(
        "Usage: /learning status | queue | topics | now | learn <topic>\n"
        "  status - Show learning system status\n"
        "  queue  - Show pending knowledge gaps\n"
        "  topics - Show recurring topics\n"
        "  now    - Run nightly learning cycle now\n"
        "  learn  - Trigger immediate learning for a topic"
    )


async def taskstatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /taskstatus <task_id>")
        return
    try:
        mission = get_mission(context.args[0])
    except Exception as exc:
        await update.message.reply_text(f"Task status failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"Task: {mission['id']}",
                f"Project: {mission['project_name']}",
                f"Status: {mission['status']}",
                f"Risk: {mission['risk']}",
                f"Plan: runtime/task_plans/{mission['id']}.md",
                f"Description: {mission['description']}",
            ]
        )
    )


async def propose(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /propose <task_id>")
        return
    try:
        proposal = create_execution_proposal_from_mission(context.args[0])
    except Exception as exc:
        await update.message.reply_text(f"Proposal creation failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"Proposal created: {proposal['id']}",
                f"Risk: {proposal['risk']}",
                "Next:",
                f"/approve {proposal['id']}",
                f"/execute {proposal['id']}",
            ]
        )
    )


async def execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /execute <proposal_id>")
        return
    try:
        result = execute_proposal_safe(context.args[0])
    except Exception as exc:
        await update.message.reply_text(f"Execution failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"Executed proposal: {result['proposal_id']}",
                f"Status: {result['status']}",
                f"Tests passed: {result['all_passed']}",
                f"Mode: {result['mode']}",
            ]
            + ([f"Applied files: {', '.join(result['applied_files'])}"] if result.get("applied_files") else [])
            + ([f"Patch: {result['patch_artifact']}"] if result.get("patch_artifact") else [])
            + ([f"Rolled back: {result['rolled_back']}"] if "rolled_back" in result else [])
        )
    )


async def memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    status_data = memory_status()
    lines = ["Memory status:"]
    lines.extend(f"- {key}: {value}" for key, value in status_data.items())
    await update.message.reply_text("\n".join(lines))


async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text("Usage: /remember <text>")
        return
    record = remember_text(text)
    await update.message.reply_text(f"Remembered: {record['id']}")


async def recall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("Usage: /recall <keyword>")
        return
    results = hybrid_recall(keyword)
    if not results:
        await update.message.reply_text(f"No memory found for: {keyword}")
        return
    lines = [f"Recall results for '{keyword}':"]
    for item in results:
        signals = []
        if item.get("matched_terms"):
            signals.append(f"matched={', '.join(item['matched_terms'])}")
        if item.get("top_terms"):
            signals.append(f"top={', '.join(item['top_terms'])}")
        lines.append(f"- {item['title']} | {item['path']} | score={item['score']}\n  {item['excerpt']}")
        if signals:
            lines.append(f"  {' | '.join(signals)}")
    await send_long_text(update.message, "\n".join(lines))


async def phase3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() != "now":
        await update.message.reply_text("Usage: /phase3 now")
        return
    summary = run_phase3_cycle()
    await update.message.reply_text(
        "\n".join(
            [
                "Phase 3 cycle completed.",
                f"Vector documents: {summary['vector_documents']}",
                f"Topic clusters: {summary['topic_clusters']}",
                f"Decisions: {summary['decisions']}",
                f"Duplicate candidates: {summary['duplicate_candidates']}",
            ]
        )
    )


async def clusters(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = cluster_topics()
    if not payload["clusters"]:
        await update.message.reply_text("No topic clusters yet.")
        return
    await update.message.reply_text(
        "\n".join(
            [f"{cluster['id']} | {cluster['label']} | members={cluster['member_count']}" for cluster in payload["clusters"]]
        )
    )


async def decisions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = list_decisions()
    if not items:
        await update.message.reply_text("No promoted decisions yet. Run /phase3 now first.")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"{decision['id']} | confidence={decision['confidence']} | evidence={decision['evidence_count']}\n  {decision['summary']}"
                for decision in items
            ]
        )
    )


async def team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    action = context.args[0].lower() if context.args else ""
    if action == "list":
        plans = list_team_plans(limit=5)
        if not plans:
            await update.message.reply_text("No mission team plans yet. Use /team plan <task_id> or /team <topic>.")
            return
        await update.message.reply_text(
            "\n".join(f"{plan['mission_id']} | {plan['project_name']} | lanes={len(plan['lanes'])}" for plan in plans)
        )
        return
    if action == "plan":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /team plan <task_id>")
            return
        try:
            plan = create_team_plan(context.args[1])
        except Exception as exc:
            await update.message.reply_text(f"Team plan failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Mission team plan ready: {plan['mission_id']}",
                    f"Project: {plan['project_name']}",
                    f"Lanes: {', '.join(lane['role'] for lane in plan['lanes'])}",
                    f"Saved: runtime/team_plans/{plan['mission_id']}.md",
                ]
            )
        )
        return
    if action == "status":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /team status <task_id>")
            return
        try:
            plan = get_team_plan(context.args[1])
        except Exception as exc:
            await update.message.reply_text(f"Team status failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Mission team plan: {plan['mission_id']}",
                    f"Project: {plan['project_name']}",
                    f"Status: {plan['status']}",
                    f"Lanes: {', '.join(lane['role'] for lane in plan['lanes'])}",
                ]
            )
        )
        return

    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("Usage: /team <topic> OR /team plan|list|status <task_id>")
        return
    brief = generate_team_brief(topic)
    await update.message.reply_text(
        "\n".join(
            [
                f"Team brief ready: {brief['topic']}",
                f"Saved: {brief['report_path']}",
                f"Memory hits: {len(brief['memory_hits'])}",
                f"Decisions used: {len(brief['decisions'])}",
            ]
        )
    )


async def ingesttools(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_event("command", "/ingesttools", topic="tools", importance="high")
    records = ingest_all_tools()
    await update.message.reply_text(f"Ingested {len(records)} tools into canonical memory.")


async def improve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_event("command", "/improve", topic="self_improvement", importance="high")
    proposal = generate_improvement_proposal()
    await update.message.reply_text(
        f"Proposal created\nID: {proposal['id']}\nTitle: {proposal['title']}\nRisk: {proposal['risk']}\nStatus: {proposal['status']}"
    )


async def proposals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = list_proposals(limit=10)
    if not items:
        await update.message.reply_text("No proposals.")
        return
    await update.message.reply_text("\n".join(f"{p['id']} | {p['risk']} | {p['title']} | {p['status']}" for p in items))


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /approve <proposal_id>")
        return
    proposal = update_proposal_status(context.args[0], "approved")
    await update.message.reply_text(f"Approved: {proposal['id']}")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /reject <proposal_id>")
        return
    proposal = update_proposal_status(context.args[0], "rejected")
    await update.message.reply_text(f"Rejected: {proposal['id']}")


async def morning(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(generate_morning_report())


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await morning(update, context)


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = request_bot_restart()
    except Exception as exc:
        await update.message.reply_text(f"Restart failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                "Restart scheduled.",
                f"Requested at: {result['requested_at']}",
                f"Delay: {result['delay_seconds']}s",
                "The bot may pause briefly, then come back under the supervisor.",
            ]
        )
    )


async def research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw_args = list(context.args)
    action = raw_args[0].lower() if raw_args else "run"
    if action == "latest":
        record = latest_research()
        if not record:
            await update.message.reply_text("No research result yet.")
            return
        await send_long_text(update.message, render_research_reply(record))
        return
    if action == "output":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            record = latest_research() if ref == "latest" else get_research(ref)
        except Exception as exc:
            await update.message.reply_text(f"Research output lookup failed: {exc}")
            return
        if not record:
            await update.message.reply_text("No research result yet.")
            return
        await send_long_text(update.message, render_research_output(record))
        return
    if action == "artifact":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            record = latest_research() if ref == "latest" else get_research(ref)
        except Exception as exc:
            await update.message.reply_text(f"Research artifact lookup failed: {exc}")
            return
        if not record:
            await update.message.reply_text("No research result yet.")
            return
        await send_long_text(update.message, render_research_artifact(record))
        return
    if action == "sessions":
        await update.message.reply_text(render_research_sessions_summary())
        return
    if action == "session":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            session = latest_research_session() if ref == "latest" else get_research_session(ref)
        except Exception as exc:
            await update.message.reply_text(f"Research session lookup failed: {exc}")
            return
        if not session:
            await update.message.reply_text("No research session yet.")
            return
        await send_long_text(update.message, render_research_session_detail(session))
        return
    if action == "start":
        query = " ".join(raw_args[1:]).strip()
        if not query:
            await update.message.reply_text("Usage: /research start <query>")
            return
        try:
            session, record = await asyncio.to_thread(start_research_session, query)
        except Exception as exc:
            await update.message.reply_text(f"Research session start failed: {exc}")
            return
        await send_long_text(
            update.message,
            "\n".join(
                [
                    f"Started research session: {session['id']}",
                    f"First research: {record['id']}",
                    render_research_reply(record),
                ]
            )
        )
        return
    if action == "continue":
        if len(raw_args) < 3:
            await update.message.reply_text("Usage: /research continue <session_id|latest> <query>")
            return
        try:
            record = await asyncio.to_thread(continue_research_session, raw_args[1], " ".join(raw_args[2:]))
        except Exception as exc:
            await update.message.reply_text(f"Research continue failed: {exc}")
            return
        await send_long_text(update.message, render_research_reply(record))
        return
    if action == "close":
        ref = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            session = close_research_session(ref)
        except Exception as exc:
            await update.message.reply_text(f"Research close failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Closed research session: {session['id']}",
                    f"Steps: {session.get('step_count', 0)}",
                ]
            )
        )
        return
    if action == "task":
        if len(raw_args) < 2:
            await update.message.reply_text("Usage: /research task <project_id> [research_id|latest]")
            return
        project_id = raw_args[1]
        research_id = raw_args[2] if len(raw_args) > 2 else "latest"
        try:
            mission = create_task_from_research(project_id=project_id, research_id=research_id)
        except Exception as exc:
            await update.message.reply_text(f"Research to task failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Task created from research: {mission['id']}",
                    f"Project: {mission['project_name']}",
                    f"Source research: {mission.get('source_research_id', research_id)}",
                ]
            )
        )
        return
    if action == "propose":
        research_id = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            proposal = create_proposal_from_research(research_id=research_id)
        except Exception as exc:
            await update.message.reply_text(f"Research to proposal failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Proposal created from research: {proposal['id']}",
                    f"Title: {proposal['title']}",
                    f"Risk: {proposal['risk']}",
                ]
            )
        )
        return
    if action == "approve":
        research_id = raw_args[1] if len(raw_args) > 1 else "latest"
        try:
            proposal = approve_research_proposal(research_id=research_id)
        except Exception as exc:
            await update.message.reply_text(f"Research approve failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Research proposal approved: {proposal['id']}",
                    f"Title: {proposal['title']}",
                    f"Status: {proposal['status']}",
                ]
            )
        )
        return

    query = " ".join(raw_args).strip()
    if not query:
        await update.message.reply_text("Usage: /research <query> | /research latest | /research output [research_id|latest] | /research artifact [research_id|latest] | /research sessions | /research session <id|latest> | /research start <query> | /research continue <session_id|latest> <query> | /research close <session_id|latest> | /research task <project_id> [research_id|latest] | /research propose [research_id|latest] | /research approve [research_id|latest]")
        return
    try:
        record = await asyncio.to_thread(run_research, query)
    except ResearchError as exc:
        await update.message.reply_text(f"Research failed: {exc}")
        return
    except Exception as exc:
        await update.message.reply_text(f"Research failed unexpectedly: {exc}")
        return
    await send_long_text(update.message, render_research_reply(record))


async def nightly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() != "now":
        await update.message.reply_text("Usage: /nightly now")
        return
    summarize_today()
    proposal = generate_improvement_proposal()
    await update.message.reply_text(f"Nightly completed. Proposal created: {proposal['id']}")


async def dream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    action = context.args[0].lower() if context.args else "now"
    if action == "now":
        result = run_dream_cycle(trigger="telegram:/dream")
        await update.message.reply_text(
            "\n".join(
                [
                    f"Dream completed: {result['id']}",
                    f"Tools: {result['light_sleep']['tool_count']} | Repos: {result['light_sleep']['repo_count']} | Notes: {result['light_sleep']['note_count']}",
                    f"Patterns: {', '.join(result['rem']['patterns']) or 'none'}",
                    "A dream is a generated memory reflection, not a scheduled task.",
                ]
            )
        )
        return
    if action == "latest":
        dream_record = latest_dream()
        if not dream_record:
            await update.message.reply_text("No dream exists yet. Run /dream now first.")
            return
        await update.message.reply_text(explain_dream(dream_record))
        return
    if action == "explain":
        dream_id = context.args[1] if len(context.args) > 1 and context.args[1].lower() != "latest" else None
        try:
            dream_record = latest_dream() if dream_id is None else None
            if dream_id:
                dream_record = get_dream(dream_id)
            await update.message.reply_text(explain_dream(dream_record))
        except Exception as exc:
            await update.message.reply_text(f"Dream explanation failed: {exc}")
        return
    if action == "task":
        project_id = context.args[1] if len(context.args) > 1 else None
        dream_id = context.args[2] if len(context.args) > 2 and context.args[2].lower() != "latest" else None
        try:
            mission = create_task_from_dream(project_id=project_id, dream_id=dream_id)
        except Exception as exc:
            await update.message.reply_text(f"Create task from dream failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"Task created from dream: {mission['id']}",
                    f"Project: {mission['project_name']}",
                    f"Source dream: {mission.get('source_dream_id', 'latest')}",
                    f"Status: {mission['status']}",
                ]
            )
        )
        return
    await update.message.reply_text(
        "Usage: /dream now | /dream latest | /dream explain [dream_id|latest] | /dream task <project_id> [dream_id|latest]"
    )


async def analyze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2 or context.args[0].lower() != "repo":
        await update.message.reply_text("Usage: /analyze repo <github_url_or_owner/repo>")
        return
    target = context.args[1]
    try:
        record, dream_result = analyze_github_repo_and_dream(target)
    except Exception as exc:
        await update.message.reply_text(f"Analyze failed: {exc}")
        return
    await update.message.reply_text(
        "\n".join(
            [
                f"Analyzed: {record['repo']}",
                f"Files: {record['file_count']}",
                f"Stack: {', '.join(record['inferred_stack']) or 'unknown'}",
                f"Saved: memory/canonical/repo_knowledge/{record['repo'].replace('/', '__').replace('-', '_')}.json",
                f"Dream: {dream_result['id']}",
            ]
        )
    )


async def rollback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /rollback <proposal_id>")
        return
    result = rollback_proposal(context.args[0])
    await update.message.reply_text(result["message"])


async def natural_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text if update.effective_message else "") or ""
    if not looks_like_plain_text_request(text):
        return
    chat_id = update.effective_chat.id if update.effective_chat else "unknown"
    user_id = _user_id(update)
    append_conversation_turn(chat_id, role="user", content=text, user_id=user_id)

    pending = get_pending_confirmation(chat_id)
    if pending:
        decision = interpret_confirmation_reply(text)
        if decision == "confirm":
            clear_pending_confirmation(chat_id)
            try:
                plan = OrchestrationPlan(**pending["plan"])
                reply = await asyncio.to_thread(execute_orchestration_plan, plan)
            except Exception as exc:
                reply = f"Confirmation failed while executing the pending action: {exc}"
            append_conversation_turn(chat_id, role="assistant", content=reply, user_id=user_id, metadata={"confirmed_action": pending.get("action")})
            await send_long_text(update.message, reply)
            return
        if decision == "cancel":
            clear_pending_confirmation(chat_id)
            reply = "Cancelled the pending execution request."
            append_conversation_turn(chat_id, role="assistant", content=reply, user_id=user_id, metadata={"confirmed_action": "cancelled"})
            await update.message.reply_text(reply)
            return
        reminder = (
            f"Pending confirmation: {pending.get('summary', pending.get('action', 'execute action'))}\n"
            "Reply with YES to continue or NO to cancel."
        )
        append_conversation_turn(chat_id, role="assistant", content=reminder, user_id=user_id, metadata={"confirmation_pending": True})
        await update.message.reply_text(reminder)
        return

    try:
        history = get_recent_context(chat_id, limit=8)
        plan = await asyncio.to_thread(
            lambda: route_message_to_plan(text, root=ROOT, conversation_history=history)
        )
        if plan.action == "execute_proposal":
            summary = plan.reply or f"Execute proposal {plan.proposal_id}"
            save_pending_confirmation(
                chat_id,
                user_id=user_id,
                action=plan.action,
                plan=plan.__dict__,
                summary=summary,
            )
            reply = (
                f"{summary}\n"
                f"Pending confirmation for proposal {plan.proposal_id or 'unknown'}.\n"
                "Reply with YES to execute or NO to cancel."
            )
        else:
            reply = await asyncio.to_thread(execute_orchestration_plan, plan)
            
            # Check if HAX-Mind couldn't understand the request (trigger auto-learning)
            if "I couldn't map that request" in reply or plan.action in ("reply", "help"):
                # Log to auto-learning system
                learning_result = handle_unknown_question(
                    question=text,
                    context={"chat_id": chat_id, "plan_action": plan.action, "plan_reply": plan.reply}
                )
                
                # If it's important or recurring, trigger immediate research
                if learning_result.get("should_trigger_learning"):
                    await update.message.reply_text(
                        f"🧠 Auto-learning triggered!\n"
                        f"This question has been asked {learning_result.get('recurring_count', 1)} time(s).\n"
                        f"Gap ID: {learning_result['gap_id']}\n"
                        f"Status: {learning_result['status']}"
                    )
                    
                    # Trigger immediate learning for important questions
                    if learning_result.get("is_important"):
                        await update.message.reply_text("🔍 Researching this topic now...")
                        try:
                            research_result = await asyncio.to_thread(
                                trigger_immediate_learning, text
                            )
                            if research_result.get("status") == "success":
                                await update.message.reply_text(
                                    f"✅ Auto-learning complete!\n"
                                    f"Proposal: {research_result.get('proposal_id')}\n"
                                    f"Title: {research_result.get('proposal_title')}\n\n"
                                    f"Use `/approve {research_result.get('proposal_id')}` to review."
                                )
                            else:
                                await update.message.reply_text(
                                    f"⚠️ Research failed: {research_result.get('error', 'Unknown error')}"
                                )
                        except Exception as e:
                            await update.message.reply_text(f"⚠️ Auto-learning error: {e}")
    except OpenRouterError as exc:
        reply = f"OpenRouter orchestration failed right now.\nError: {exc}"
    except Exception as exc:
        reply = f"Natural-language orchestration failed: {exc}"
    append_conversation_turn(chat_id, role="assistant", content=reply, user_id=user_id)
    await send_long_text(update.message, reply)


def _write_lifecycle(message: str) -> None:
    ensure_dir(BOT_LOG_PATH.parent)
    with BOT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {message}\n")


def _write_error_log(message: str) -> None:
    ensure_dir(BOT_ERR_LOG_PATH.parent)
    with BOT_ERR_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {message}\n")


def _write_pid() -> None:
    ensure_dir(PID_PATH.parent)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    _write_lifecycle(f"telegram bot started with pid={os.getpid()}")


def _clear_pid() -> None:
    if PID_PATH.exists():
        current = PID_PATH.read_text(encoding="utf-8", errors="ignore").strip()
        if current == str(os.getpid()):
            PID_PATH.unlink(missing_ok=True)
    _write_lifecycle("telegram bot stopped")


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = f"telegram bot error: {context.error!r}"
    _write_error_log(message)
    _write_lifecycle(message)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not found. Copy .env.example to .env and set it yourself.")
    instance_lock = BotInstanceLock()
    instance_lock.acquire()
    _write_pid()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(_on_error)
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("auth", auth))
    app.add_handler(CommandHandler("start", require_auth(start)))
    app.add_handler(CommandHandler("status", require_auth(status)))
    app.add_handler(CommandHandler("health", require_auth(health)))
    app.add_handler(CommandHandler("restart", require_auth(restart)))
    app.add_handler(CommandHandler("research", require_auth(research)))
    app.add_handler(CommandHandler("project", require_auth(project)))
    app.add_handler(CommandHandler("task", require_auth(task)))
    app.add_handler(CommandHandler("tasks", require_auth(tasks)))
    app.add_handler(CommandHandler("taskstatus", require_auth(taskstatus)))
    app.add_handler(CommandHandler("taskdone", require_auth(taskdone)))
    app.add_handler(CommandHandler("picoclaw", require_auth(picoclaw)))
    app.add_handler(CommandHandler("cli", require_auth(cli)))
    app.add_handler(CommandHandler("learning", require_auth(learning)))
    app.add_handler(CommandHandler("propose", require_auth(propose)))
    app.add_handler(CommandHandler("execute", require_auth(execute)))
    app.add_handler(CommandHandler("memory", require_auth(memory)))
    app.add_handler(CommandHandler("remember", require_auth(remember)))
    app.add_handler(CommandHandler("recall", require_auth(recall_command)))
    app.add_handler(CommandHandler("phase3", require_auth(phase3)))
    app.add_handler(CommandHandler("clusters", require_auth(clusters)))
    app.add_handler(CommandHandler("decisions", require_auth(decisions)))
    app.add_handler(CommandHandler("team", require_auth(team)))
    app.add_handler(CommandHandler("tools", require_auth(tools)))
    app.add_handler(CommandHandler("ingesttools", require_auth(ingesttools)))
    app.add_handler(CommandHandler("improve", require_auth(improve)))
    app.add_handler(CommandHandler("proposals", require_auth(proposals)))
    app.add_handler(CommandHandler("approve", require_auth(approve)))
    app.add_handler(CommandHandler("reject", require_auth(reject)))
    app.add_handler(CommandHandler("rollback", require_auth(rollback)))
    app.add_handler(CommandHandler("morning", require_auth(morning)))
    app.add_handler(CommandHandler("report", require_auth(report)))
    app.add_handler(CommandHandler("nightly", require_auth(nightly)))
    app.add_handler(CommandHandler("dream", require_auth(dream)))
    app.add_handler(CommandHandler("analyze", require_auth(analyze)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, require_auth(natural_chat)))
    try:
        app.run_polling()
    finally:
        _clear_pid()
        instance_lock.release()


if __name__ == "__main__":
    main()
