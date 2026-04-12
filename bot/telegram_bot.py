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
from engine.cli_bridge import (
    create_cli_improvement_proposal,
    get_cli_job,
    open_cli_session,
    render_cli_jobs_summary,
    render_cli_tools_summary,
    run_cli_once,
)
from engine.project_manager import list_projects, register_project
from engine.repo_analyzer import analyze_github_repo_and_dream
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
        "HAX-Mind ready. Commands: /whoami /auth /status /restart /project add|list /task <project> <work> /tasks /taskstatus <id> /propose <task_id> /approve <proposal_id> /execute <proposal_id> /picoclaw status|worker status|plan|jobs|queue <approved_proposal_id> /cli tools|jobs|status <job_id>|open <tool> <prompt>|run <tool> <prompt>|improve /memory /recall <query> /phase3 now /clusters /decisions /team <topic> | /team plan|list|status <task_id> /dream now|latest|explain [dream_id|latest]|task <project_id> [dream_id|latest] /analyze repo <url> /report\nStructured task syntax for guarded real apply: /task <project_id> append|replace|create|delete <path> :: <content>"
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
    await update.message.reply_text("\n".join(f"{m['id']} | {m['project_name']} | {m['status']} | {m['description'][:80]}" for m in missions))


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
    action = context.args[0].lower() if context.args else "tools"
    if action == "tools":
        await update.message.reply_text(render_cli_tools_summary())
        return
    if action == "jobs":
        await update.message.reply_text(render_cli_jobs_summary())
        return
    if action == "status":
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /cli status <job_id>")
            return
        try:
            job = get_cli_job(context.args[1])
        except Exception as exc:
            await update.message.reply_text(f"CLI job lookup failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"CLI job: {job['id']}",
                    f"Tool: {job['tool']}",
                    f"Mode: {job['mode']}",
                    f"Status: {job['status']}",
                    *( [f"Output: {job['output_path']}"] if job.get("output_path") else [] ),
                    *( [f"Exit code: {job['exit_code']}"] if 'exit_code' in job else [] ),
                ]
            )
        )
        return
    if action == "open":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /cli open <codex|omx|gemini|kimi> <prompt>")
            return
        try:
            job = open_cli_session(context.args[1], " ".join(context.args[2:]))
        except Exception as exc:
            await update.message.reply_text(f"CLI open failed: {exc}")
            return
        await update.message.reply_text(
            f"Opened {job['tool']} interactive CLI.\nJob: {job['id']}\nPrompt: {job['prompt'][:200]}"
        )
        return
    if action == "run":
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /cli run <codex|omx|gemini|kimi> <prompt>")
            return
        try:
            job = run_cli_once(context.args[1], " ".join(context.args[2:]))
        except Exception as exc:
            await update.message.reply_text(f"CLI run failed: {exc}")
            return
        await update.message.reply_text(
            "\n".join(
                [
                    f"CLI job completed: {job['id']}",
                    f"Tool: {job['tool']}",
                    f"Status: {job['status']}",
                    *( [f"Output: {job['output_path']}"] if job.get("output_path") else [] ),
                    *( [job['stdout_excerpt'][:1500]] if job.get("stdout_excerpt") else [] ),
                ]
            )[:4000]
        )
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
    await update.message.reply_text("Usage: /cli tools | jobs | status <job_id> | open <tool> <prompt> | run <tool> <prompt> | improve")


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
                f"Description: {mission['description'][:500]}",
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
    for item in results[:5]:
        signals = []
        if item.get("matched_terms"):
            signals.append(f"matched={', '.join(item['matched_terms'][:4])}")
        if item.get("top_terms"):
            signals.append(f"top={', '.join(item['top_terms'][:4])}")
        lines.append(f"- {item['title']} | {item['path']} | score={item['score']}\n  {item['excerpt'][:220]}")
        if signals:
            lines.append(f"  {' | '.join(signals)}")
    await update.message.reply_text("\n".join(lines))


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
            [f"{cluster['id']} | {cluster['label']} | members={cluster['member_count']}" for cluster in payload["clusters"][:5]]
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
                f"{decision['id']} | confidence={decision['confidence']} | evidence={decision['evidence_count']}\n  {decision['summary'][:180]}"
                for decision in items[:5]
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
                    f"Patterns: {', '.join(result['rem']['patterns'][:8]) or 'none'}",
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
            await update.message.reply_text(reply[:4000])
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
    except OpenRouterError as exc:
        reply = f"OpenRouter orchestration failed right now.\nError: {exc}"
    except Exception as exc:
        reply = f"Natural-language orchestration failed: {exc}"
    append_conversation_turn(chat_id, role="assistant", content=reply, user_id=user_id)
    await update.message.reply_text(reply[:4000])


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
    app.add_handler(CommandHandler("project", require_auth(project)))
    app.add_handler(CommandHandler("task", require_auth(task)))
    app.add_handler(CommandHandler("tasks", require_auth(tasks)))
    app.add_handler(CommandHandler("taskstatus", require_auth(taskstatus)))
    app.add_handler(CommandHandler("taskdone", require_auth(taskdone)))
    app.add_handler(CommandHandler("picoclaw", require_auth(picoclaw)))
    app.add_handler(CommandHandler("cli", require_auth(cli)))
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
