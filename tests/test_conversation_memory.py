from pathlib import Path

from engine.confirmation_store import (
    clear_pending_confirmation,
    get_pending_confirmation,
    interpret_confirmation_reply,
    save_pending_confirmation,
)
from engine.conversation_memory import append_conversation_turn, get_recent_context, read_conversation


def test_conversation_memory_persists_recent_turns(tmp_path: Path) -> None:
    append_conversation_turn(123, role="user", content="hello", root=tmp_path)
    append_conversation_turn(123, role="assistant", content="hi", root=tmp_path)

    turns = read_conversation(123, root=tmp_path)
    recent = get_recent_context(123, root=tmp_path, limit=2)

    assert len(turns) == 2
    assert recent == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_confirmation_store_roundtrip(tmp_path: Path) -> None:
    save_pending_confirmation(
        123,
        user_id=555,
        action="execute_proposal",
        plan={"action": "execute_proposal", "proposal_id": "prop_1", "reply": "execute it"},
        summary="Execute prop_1",
        root=tmp_path,
    )

    pending = get_pending_confirmation(123, root=tmp_path)
    assert pending is not None
    assert pending["action"] == "execute_proposal"
    assert pending["plan"]["proposal_id"] == "prop_1"

    clear_pending_confirmation(123, root=tmp_path)
    assert get_pending_confirmation(123, root=tmp_path) is None


def test_confirmation_reply_interpretation() -> None:
    assert interpret_confirmation_reply("YES") == "confirm"
    assert interpret_confirmation_reply("ยกเลิก") == "cancel"
    assert interpret_confirmation_reply("maybe later") == "unknown"
