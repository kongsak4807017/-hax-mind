from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from engine.auth import auth_status_for_user, is_authorized_user
from engine.github_ingestor import ingest_all_tools
from engine.dreaming import memory_status, remember_text, run_dream_cycle
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
from engine.picoclaw_manager import list_remote_jobs, picoclaw_plan, picoclaw_status, queue_proposal_for_remote_safe_execution
from engine.proposal_engine import list_proposals, update_proposal_status
from engine.apply_engine import execute_proposal_safe
from engine.project_manager import list_projects, register_project
from engine.repo_analyzer import analyze_github_repo_and_dream
from engine.research_team import generate_team_brief
from engine.rollback_engine import rollback_proposal
from engine.self_improvement_engine import generate_improvement_proposal
from engine.team_orchestrator import create_team_plan, get_team_plan, list_team_plans
from engine.tool_registry import iter_tools
from engine.utils import ROOT, ensure_dir, now_iso, read_env_file

read_env_file()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PID_PATH = ROOT / "runtime" / "telegram_bot.pid"
BOT_LOG_PATH = ROOT / "runtime" / "logs" / "telegram_bot.lifecycle.log"


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
        "HAX-Mind ready. Commands: /whoami /auth /status /project add|list /task <project> <work> /tasks /taskstatus <id> /propose <task_id> /approve <proposal_id> /execute <proposal_id> /picoclaw status|plan|jobs|queue <approved_proposal_id> /memory /recall <query> /phase3 now /clusters /decisions /team <topic> | /team plan|list|status <task_id> /dream now /analyze repo <url> /report\nStructured task syntax for guarded real apply: /task <project_id> append|replace|create|delete <path> :: <content>"
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
                    "Use /picoclaw plan, /picoclaw jobs, or /picoclaw queue <approved_proposal_id>.",
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
    await update.message.reply_text("Usage: /picoclaw status | plan | jobs | queue <approved_proposal_id>")


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


async def nightly(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() != "now":
        await update.message.reply_text("Usage: /nightly now")
        return
    summarize_today()
    proposal = generate_improvement_proposal()
    await update.message.reply_text(f"Nightly completed. Proposal created: {proposal['id']}")


async def dream(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and context.args[0].lower() != "now":
        await update.message.reply_text("Usage: /dream now")
        return
    result = run_dream_cycle(trigger="telegram:/dream")
    await update.message.reply_text(
        "\n".join(
            [
                f"Dream completed: {result['id']}",
                f"Tools: {result['light_sleep']['tool_count']} | Repos: {result['light_sleep']['repo_count']} | Notes: {result['light_sleep']['note_count']}",
                f"Patterns: {', '.join(result['rem']['patterns'][:8]) or 'none'}",
            ]
        )
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


def _write_lifecycle(message: str) -> None:
    ensure_dir(BOT_LOG_PATH.parent)
    with BOT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"[{now_iso()}] {message}\n")


def _write_pid() -> None:
    ensure_dir(PID_PATH.parent)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    _write_lifecycle(f"telegram bot started with pid={os.getpid()}")


def _clear_pid() -> None:
    if PID_PATH.exists():
        PID_PATH.unlink(missing_ok=True)
    _write_lifecycle("telegram bot stopped")


def main() -> None:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not found. Copy .env.example to .env and set it yourself.")
    _write_pid()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("auth", auth))
    app.add_handler(CommandHandler("start", require_auth(start)))
    app.add_handler(CommandHandler("status", require_auth(status)))
    app.add_handler(CommandHandler("health", require_auth(health)))
    app.add_handler(CommandHandler("project", require_auth(project)))
    app.add_handler(CommandHandler("task", require_auth(task)))
    app.add_handler(CommandHandler("tasks", require_auth(tasks)))
    app.add_handler(CommandHandler("taskstatus", require_auth(taskstatus)))
    app.add_handler(CommandHandler("taskdone", require_auth(taskdone)))
    app.add_handler(CommandHandler("picoclaw", require_auth(picoclaw)))
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
    try:
        app.run_polling()
    finally:
        _clear_pid()


if __name__ == "__main__":
    main()
