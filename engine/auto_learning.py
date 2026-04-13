"""
HAX-Mind Auto-Learning System
เรียนรู้อัตโนมัติจากคำถามและสถานการณ์ที่ตอบสนองไม่ได้
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from engine.memory_analyzer import log_event
from engine.memory_store import initialize_memory_dirs, write_json, write_text
from engine.proposal_engine import create_proposal
from engine.research_engine import run_research
from engine.utils import ROOT, ensure_dir, now_iso

LEARNING_QUEUE_DIR = ROOT / "runtime" / "learning_queue"
KNOWLEDGE_GAPS_DIR = ROOT / "memory" / "knowledge_gaps"
AUTO_LEARNED_NOTES = ROOT / "memory" / "canonical" / "notes" / "auto_learned.md"

# Threshold สำหรับ trigger auto-learning
RECURRING_THRESHOLD = 3  # เจอคำถามคล้ายกัน 3 ครั้งขึ้นไป
IMPORTANCE_KEYWORDS = ["error", "fail", "bug", "crash", "security", "important", "urgent"]


def _learning_gap_path(gap_id: str, root: Path = ROOT) -> Path:
    return root / "runtime" / "learning_queue" / f"{gap_id}.json"


def _normalize_question(text: str) -> str:
    """ Normalize คำถามเพื่อเปรียบเทียบความคล้ายกัน """
    # ลบตัวอักษรพิเศษ และแปลงเป็นพิมพ์เล็ก
    text = re.sub(r"[^\w\s]", "", text.lower())
    # ลบคำฟiller
    fillers = {"the", "a", "an", "is", "are", "was", "were", "been", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while", "ที่", "ใน", "ของ", "และ", "หรือ", "แต่", "กับ", "จาก", "โดย", "ว่า", "นี้", "มี", "เป็น", "ได้", "จะ", "ให้", "ต้อง", "คือ", "เมื่อ", "ถ้า"}
    words = [w for w in text.split() if w not in fillers and len(w) > 2]
    return " ".join(sorted(set(words)))


def _extract_topic_keywords(text: str) -> list[str]:
    """ ดึง keywords จากคำถาม """
    # หาคำที่ขึ้นต้นด้วยตัวพิมพ์ใหญ่หรือคำเฉพาะทาง
    words = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b|\b[a-z]+(?:_[a-z]+)+\b', text)
    return list(set(words))[:5]


def _is_important_question(text: str) -> bool:
    """ ตรวจสอบว่าคำถามสำคัญหรือไม่ """
    text_lower = text.lower()
    return any(kw in text_lower for kw in IMPORTANCE_KEYWORDS)


def _calculate_similarity(text1: str, text2: str) -> float:
    """ คำนวณความคล้ายคลึงระหว่างคำถาม (0-1) """
    norm1 = set(_normalize_question(text1).split())
    norm2 = set(_normalize_question(text2).split())
    if not norm1 or not norm2:
        return 0.0
    intersection = norm1 & norm2
    union = norm1 | norm2
    return len(intersection) / len(union)


def handle_unknown_question(question: str, context: dict | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    """
    เรียกเมื่อเจอคำถามที่ตอบไม่ได้
    บันทึกลง queue และตรวจสอบว่าควร trigger auto-learning ทันทีหรือไม่
    """
    ensure_dir(root / "runtime" / "learning_queue")
    ensure_dir(root / "memory" / "knowledge_gaps")
    
    gap_id = f"gap_{now_iso()[:10].replace('-', '')}_{uuid.uuid4().hex[:8]}"
    normalized = _normalize_question(question)
    
    record = {
        "id": gap_id,
        "created_at": now_iso(),
        "question": question,
        "normalized": normalized,
        "keywords": _extract_topic_keywords(question),
        "context": context or {},
        "status": "pending",
        "recurring_count": 1,
        "is_important": _is_important_question(question),
    }
    
    # ตรวจสอบว่ามีคำถามคล้ายกันใน queue หรือไม่
    similar_gaps = find_similar_gaps(normalized, threshold=0.7, root=root)
    if similar_gaps:
        # อัพเดต count ให้กับ gap ที่คล้ายกันที่สุด
        most_similar = similar_gaps[0]
        most_similar["recurring_count"] = most_similar.get("recurring_count", 1) + 1
        most_similar["last_seen"] = now_iso()
        _save_gap(most_similar, root=root)
        record["related_to"] = most_similar["id"]
        record["status"] = "merged"
    else:
        _save_gap(record, root=root)
    
    # บันทึก event
    log_event(
        "knowledge_gap",
        f"Unknown question: {question[:100]}...",
        topic="auto_learning",
        importance="high" if record["is_important"] else "normal"
    )
    
    # ถ้าสำคัญมาก หรือ เป็น pattern ซ้ำ → trigger ทันที
    should_trigger = (
        record.get("recurring_count", 1) >= RECURRING_THRESHOLD or
        record["is_important"]
    )
    
    return {
        "gap_id": gap_id,
        "status": record["status"],
        "recurring_count": record.get("recurring_count", 1),
        "is_important": record["is_important"],
        "should_trigger_learning": should_trigger,
        "similar_gaps_found": len(similar_gaps),
    }


def find_similar_gaps(normalized_text: str, threshold: float = 0.7, *, root: Path = ROOT) -> list[dict]:
    """ หา knowledge gaps ที่คล้ายกัน """
    similar = []
    learning_queue_dir = root / "runtime" / "learning_queue"
    if not learning_queue_dir.exists():
        return similar
    
    for path in learning_queue_dir.glob("gap_*.json"):
        try:
            gap = json.loads(path.read_text(encoding="utf-8"))
            similarity = _calculate_similarity(normalized_text, gap.get("normalized", ""))
            if similarity >= threshold:
                gap["_similarity"] = similarity
                similar.append(gap)
        except (json.JSONDecodeError, KeyError):
            continue
    
    return sorted(similar, key=lambda x: x.get("_similarity", 0), reverse=True)


def _save_gap(record: dict, root: Path = ROOT) -> dict:
    """ บันทึก knowledge gap ลงไฟล์ """
    path = _learning_gap_path(record["id"], root=root)
    ensure_dir(path.parent)
    write_json(path, record)
    return record


def get_pending_gaps(*, root: Path = ROOT, limit: int = 100) -> list[dict]:
    """ ดึงรายการ knowledge gaps ที่ยัง pending """
    learning_queue_dir = root / "runtime" / "learning_queue"
    ensure_dir(learning_queue_dir)
    gaps = []
    for path in sorted(learning_queue_dir.glob("gap_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            gap = json.loads(path.read_text(encoding="utf-8"))
            if gap.get("status") in ("pending", "merged"):
                gaps.append(gap)
        except json.JSONDecodeError:
            continue
    return gaps


def get_recurring_topics(*, root: Path = ROOT, min_count: int = RECURRING_THRESHOLD) -> list[dict]:
    """ หาหัวข้อที่ถูกถามซ้ำบ่อย """
    gaps = get_pending_gaps(root=root)
    topic_counter = Counter()
    
    for gap in gaps:
        count = gap.get("recurring_count", 1)
        keywords = gap.get("keywords", [])
        for kw in keywords:
            topic_counter[kw] += count
    
    return [
        {"topic": topic, "count": count}
        for topic, count in topic_counter.most_common(10)
        if count >= min_count
    ]


def trigger_immediate_learning(question: str, *, root: Path = ROOT) -> dict[str, Any]:
    """
    Trigger research และสร้าง proposal ทันที
    ใช้เมื่อพบว่าคำถามสำคัญหรือเป็น pattern ซ้ำ
    """
    log_event("auto_learning", f"Triggering immediate learning for: {question[:100]}...", topic="auto_learning", importance="high")
    
    # 1. Research หาคำตอบ
    try:
        research_result = run_research(f"{question} latest research 2024 2025")
    except Exception as e:
        return {
            "status": "failed",
            "stage": "research",
            "error": str(e),
        }
    
    # 2. สร้าง proposal ปรับปรุง
    try:
        proposal = create_learning_proposal(question, research_result, root=root)
    except Exception as e:
        return {
            "status": "failed",
            "stage": "proposal",
            "error": str(e),
            "research_summary": research_result.get("summary", "")[:500],
        }
    
    return {
        "status": "success",
        "proposal_id": proposal["id"],
        "proposal_title": proposal["title"],
        "research_summary": research_result.get("summary", "")[:500],
    }


def create_learning_proposal(question: str, research_result: dict, *, root: Path = ROOT) -> dict:
    """ สร้าง proposal จากผลการ research """
    summary = research_result.get("summary", "No summary available")
    
    proposal = create_proposal(
        title=f"[Auto-Learning] {question[:50]}...",
        component="knowledge_base",
        problem=f"HAX-Mind ไม่สามารถตอบคำถามได้: {question}",
        root_cause="ระบบยังไม่มีความรู้หรือ capability สำหรับคำถามนี้",
        solution=f"\nจากการ research พบว่า:\n{summary[:1000]}\n\nแนะนำให้:\n1. บันทึกความรู้ลง memory\n2. ปรับปรุง orchestrator ให้รู้จักคำถามประเภทนี้\n3. พิจารณาเพิ่ม command หรือ capability ใหม่",
        expected_impact="HAX-Mind จะสามารถตอบคำถามประเภทนี้ได้ในอนาคต และป้องกันไม่ให้เกิด knowledge gap ซ้ำ",
        risk="low",
        files_to_modify=[
            "memory/canonical/notes/auto_learned.md",
            "engine/orchestrator.py",
        ],
        tests_to_run=["tests/test_orchestrator.py"],
        rollback_plan="ลบข้อมูลที่เพิ่มเข้าไปใน memory และ revert การเปลี่ยนแปลงใน orchestrator",
        metadata={
            "auto_learning": True,
            "source_question": question,
            "research_id": research_result.get("id"),
        },
        root=root,
    )
    
    return proposal


def nightly_learning_cycle(*, root: Path = ROOT) -> dict[str, Any]:
    """
    Learning cycle ที่รันทุกคืน
    วิเคราะห์ knowledge gaps และสร้าง proposals
    """
    log_event("auto_learning", "Starting nightly learning cycle", topic="auto_learning", importance="high")
    
    # 1. หาหัวข้อที่ถูกถามซ้ำ
    recurring = get_recurring_topics(root=root, min_count=RECURRING_THRESHOLD)
    
    # 2. หา gaps ที่สำคัญ
    pending = get_pending_gaps(root=root)
    important_gaps = [g for g in pending if g.get("is_important") and g.get("status") == "pending"]
    
    results = {
        "recurring_topics": recurring,
        "important_gaps_count": len(important_gaps),
        "proposals_created": [],
        "errors": [],
    }
    
    # 3. สร้าง proposals สำหรับ recurring topics
    for topic_info in recurring[:3]:  # จำกัด 3 อันดับแรก
        try:
            # หา gap ที่เกี่ยวข้องกับ topic นี้
            related_gaps = [g for g in pending if topic_info["topic"] in g.get("keywords", [])]
            if related_gaps:
                sample_question = related_gaps[0]["question"]
                research_result = run_research(f"{topic_info['topic']} AI systems latest research")
                proposal = create_learning_proposal(sample_question, research_result, root=root)
                results["proposals_created"].append({
                    "topic": topic_info["topic"],
                    "proposal_id": proposal["id"],
                })
                
                # อัพเดต status ของ gaps ที่เกี่ยวข้อง
                for gap in related_gaps:
                    gap["status"] = "researched"
                    gap["proposal_id"] = proposal["id"]
                    _save_gap(gap, root=root)
                    
        except Exception as e:
            results["errors"].append({"topic": topic_info["topic"], "error": str(e)})
    
    # 4. สร้าง proposals สำหรับ important gaps
    for gap in important_gaps[:2]:  # จำกัด 2 อันดับแรก
        if gap.get("status") != "pending":
            continue
        try:
            result = trigger_immediate_learning(gap["question"], root=root)
            if result["status"] == "success":
                results["proposals_created"].append({
                    "gap_id": gap["id"],
                    "proposal_id": result["proposal_id"],
                })
                gap["status"] = "researched"
                _save_gap(gap, root=root)
        except Exception as e:
            results["errors"].append({"gap_id": gap["id"], "error": str(e)})
    
    log_event(
        "auto_learning",
        f"Nightly cycle complete. Created {len(results['proposals_created'])} proposals",
        topic="auto_learning",
        importance="high"
    )
    
    return results


def get_learning_status(*, root: Path = ROOT) -> dict[str, Any]:
    """ ดูสถานะการเรียนรู้ปัจจุบัน """
    pending = get_pending_gaps(root=root)
    recurring = get_recurring_topics(root=root, min_count=2)
    
    return {
        "pending_gaps": len(pending),
        "recurring_topics": recurring,
        "ready_for_learning": len([g for g in pending if g.get("recurring_count", 1) >= RECURRING_THRESHOLD]),
        "last_updated": now_iso(),
    }


def render_learning_summary(*, root: Path = ROOT) -> str:
    """ สรุปสถานะการเรียนรู้สำหรับแสดงใน Telegram """
    status = get_learning_status(root=root)
    
    lines = [
        "🧠 Auto-Learning Status",
        "",
        f"Pending knowledge gaps: {status['pending_gaps']}",
        f"Ready for learning: {status['ready_for_learning']}",
        "",
    ]
    
    if status["recurring_topics"]:
        lines.append("Recurring topics:")
        for topic in status["recurring_topics"][:5]:
            lines.append(f"  • {topic['topic']}: {topic['count']} times")
    else:
        lines.append("No recurring topics detected yet.")
    
    return "\n".join(lines)
