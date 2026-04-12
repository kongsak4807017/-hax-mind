from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

from engine.memory_store import append_raw_log, initialize_memory_dirs, write_json, write_text
from engine.utils import ROOT, now_iso

DREAMS_DIRNAME = "dreams"


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()[:80] or "memory"


def _read_json_files(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    records: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["_path"] = str(path)
            records.append(payload)
        except json.JSONDecodeError:
            continue
    return records


def _read_raw_log_items(root: Path = ROOT, limit: int = 200) -> list[dict]:
    log_dir = root / "memory" / "raw_logs"
    if not log_dir.exists():
        return []
    items: list[dict] = []
    for path in sorted(log_dir.glob("*.log"), key=lambda p: p.name, reverse=True):
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                item = json.loads(line)
                item["_path"] = str(path)
                items.append(item)
            except json.JSONDecodeError:
                continue
            if len(items) >= limit:
                return items
    return items


def _canonical_search_dirs(root: Path) -> list[Path]:
    return [
        root / "memory" / "canonical" / "tools",
        root / "memory" / "canonical" / "repo_knowledge",
        root / "memory" / "canonical" / "notes",
        root / "memory" / "canonical" / "dreams",
        root / "memory" / "canonical" / "decisions",
    ]


def _dreams_dir(root: Path = ROOT) -> Path:
    return root / "memory" / "canonical" / DREAMS_DIRNAME


def _record_title(payload: dict[str, Any], path: Path) -> str:
    return payload.get("name") or payload.get("repo") or payload.get("id") or path.stem


def _record_type(payload: dict[str, Any], path: Path) -> str:
    return payload.get("type") or payload.get("role") or path.parent.name


def _record_search_text(payload: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", json.dumps(payload, ensure_ascii=False)).strip()


def _build_excerpt(search_text: str, matched_terms: list[str], radius: int = 140) -> str:
    lowered = search_text.lower()
    position = 0
    for term in matched_terms:
        position = lowered.find(term.lower())
        if position >= 0:
            break
    excerpt = search_text[max(0, position - radius) : position + radius] if search_text else ""
    return re.sub(r"\s+", " ", excerpt).strip()[:320]


def rebuild_recall_index(root: Path = ROOT) -> dict[str, Any]:
    initialize_memory_dirs(root)
    documents: dict[str, dict[str, Any]] = {}
    terms: dict[str, dict[str, int]] = {}

    for directory in _canonical_search_dirs(root):
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            search_text = _record_search_text(payload)
            doc_id = str(path.relative_to(root))
            title = _record_title(payload, path)
            kind = _record_type(payload, path)
            documents[doc_id] = {
                "path": doc_id,
                "title": title,
                "type": kind,
                "search_text": search_text,
                "token_count": len(_tokenize(search_text)),
            }
            for token, frequency in Counter(_tokenize(search_text)).items():
                terms.setdefault(token, {})[doc_id] = frequency

    index = {
        "updated_at": now_iso(),
        "document_count": len(documents),
        "term_count": len(terms),
        "documents": documents,
        "terms": terms,
    }
    write_json(root / "memory" / "indexes" / "recall_index.json", index)
    return index


def _expand_query_terms(query_tokens: list[str], vocabulary: set[str]) -> dict[str, set[str]]:
    expanded: dict[str, set[str]] = {}
    vocabulary_list = sorted(vocabulary)
    for token in query_tokens:
        matches: set[str] = set()
        if token in vocabulary:
            matches.add(token)
        prefix = token[: max(3, min(5, len(token)))]
        matches.update(term for term in vocabulary if term.startswith(prefix))
        matches.update(difflib.get_close_matches(token, vocabulary_list, n=3, cutoff=0.82))
        expanded[token] = matches or {token}
    return expanded


def _top_terms(text: str, limit: int = 8) -> list[str]:
    banned = {
        "https",
        "github",
        "memory",
        "source",
        "path",
        "type",
        "topic",
        "created_at",
        "updated_at",
        "content",
        "notes",
        "dreams",
        "tools",
        "repos",
        "decisions",
        "title",
        "role",
        "system",
    }
    counter = Counter(token for token in _tokenize(text) if token not in banned)
    return [token for token, _ in counter.most_common(limit)]


def _embedding_dimensions() -> int:
    return 96


def _embed_text(text: str, dimensions: int | None = None) -> list[float]:
    dimensions = dimensions or _embedding_dimensions()
    vector = [0.0] * dimensions
    counter = Counter(_tokenize(text))
    if not counter:
        return vector
    for token, frequency in counter.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        hashed = int.from_bytes(digest, "big")
        index = hashed % dimensions
        sign = -1.0 if hashed & 1 else 1.0
        weight = 1.0 + math.log1p(frequency)
        vector[index] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [round(value / norm, 6) for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _safe_cluster_label(terms: list[str], fallback: str) -> str:
    label_terms = [term for term in terms if term][:3]
    return " / ".join(label_terms) or fallback


def _generated_decision_path(root: Path, decision_id: str) -> Path:
    return root / "memory" / "canonical" / "decisions" / f"{decision_id}.json"


def promote_decisions(root: Path = ROOT) -> list[dict[str, Any]]:
    initialize_memory_dirs(root)
    repeated_items: dict[str, dict[str, Any]] = {}

    for path in sorted((root / "memory" / "canonical" / "dreams").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for statement in payload.get("rem", {}).get("next_actions", []) + payload.get("rem", {}).get("insights", []):
            normalized = re.sub(r"\s+", " ", statement.strip())
            if not normalized:
                continue
            bucket = repeated_items.setdefault(
                normalized,
                {"statement": normalized, "sources": [], "count": 0, "kind": "dream_guidance"},
            )
            bucket["sources"].append(str(path.relative_to(root)))
            bucket["count"] += 1

    for path in sorted((root / "memory" / "canonical" / "notes").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        normalized = re.sub(r"\s+", " ", str(payload.get("content", "")).strip().lower())
        if not normalized:
            continue
        bucket = repeated_items.setdefault(
            normalized,
            {"statement": str(payload.get("content", "")).strip(), "sources": [], "count": 0, "kind": "repeated_note"},
        )
        bucket["sources"].append(str(path.relative_to(root)))
        bucket["count"] += 1

    promoted: list[dict[str, Any]] = []
    for item in repeated_items.values():
        if item["count"] < 2:
            continue
        decision_id = f"decision_{_safe_id(item['statement'][:60])}"
        decision = {
            "id": decision_id,
            "type": "promoted_decision",
            "source": "phase3_memory_intelligence",
            "statement": item["statement"],
            "summary": item["statement"],
            "confidence": "medium" if item["count"] == 2 else "high",
            "occurrences": item["count"],
            "kind": item["kind"],
            "top_terms": _top_terms(item["statement"], limit=5),
            "source_paths": item["sources"],
            "promoted_at": now_iso(),
        }
        write_json(_generated_decision_path(root, decision_id), decision)
        promoted.append(decision)
    return promoted


def rebuild_vector_index(root: Path = ROOT, recall_index: dict[str, Any] | None = None) -> dict[str, Any]:
    initialize_memory_dirs(root)
    recall_index = recall_index or rebuild_recall_index(root)
    documents: dict[str, dict[str, Any]] = {}
    for doc_id, document in recall_index["documents"].items():
        embedding = _embed_text(document["search_text"])
        documents[doc_id] = {
            "path": document["path"],
            "title": document["title"],
            "type": document["type"],
            "top_terms": _top_terms(document["search_text"]),
            "embedding": embedding,
        }
    vector_index = {
        "updated_at": now_iso(),
        "dimensions": _embedding_dimensions(),
        "document_count": len(documents),
        "documents": documents,
    }
    write_json(root / "memory" / "indexes" / "vector_index.json", vector_index)
    return vector_index


def build_topic_clusters(root: Path = ROOT, vector_index: dict[str, Any] | None = None) -> dict[str, Any]:
    initialize_memory_dirs(root)
    vector_index = vector_index or rebuild_vector_index(root)
    clusters: list[dict[str, Any]] = []

    for document in vector_index["documents"].values():
        assigned_cluster: dict[str, Any] | None = None
        best_similarity = 0.0
        for cluster in clusters:
            similarity = _cosine_similarity(document["embedding"], cluster["centroid"])
            if similarity >= 0.58 and similarity > best_similarity:
                assigned_cluster = cluster
                best_similarity = similarity
        if assigned_cluster is None:
            assigned_cluster = {
                "id": f"cluster_{len(clusters) + 1:03d}",
                "documents": [],
                "centroid": document["embedding"][:],
                "term_counter": Counter(),
            }
            clusters.append(assigned_cluster)
        assigned_cluster["documents"].append(
            {
                "path": document["path"],
                "title": document["title"],
                "type": document["type"],
                "top_terms": document["top_terms"],
            }
        )
        assigned_cluster["term_counter"].update(document["top_terms"])
        doc_count = len(assigned_cluster["documents"])
        if doc_count > 1:
            assigned_cluster["centroid"] = [
                round(((current * (doc_count - 1)) + new_value) / doc_count, 6)
                for current, new_value in zip(assigned_cluster["centroid"], document["embedding"])
            ]

    serializable_clusters = []
    for cluster in clusters:
        common_terms = [term for term, _ in cluster["term_counter"].most_common(4)]
        serializable_clusters.append(
            {
                "id": cluster["id"],
                "label": _safe_cluster_label(common_terms, cluster["documents"][0]["title"]),
                "document_count": len(cluster["documents"]),
                "top_terms": common_terms,
                "documents": cluster["documents"],
            }
        )
    payload = {"updated_at": now_iso(), "cluster_count": len(serializable_clusters), "clusters": serializable_clusters}
    write_json(root / "memory" / "indexes" / "topic_clusters.json", payload)
    return payload


def detect_duplicate_candidates(root: Path = ROOT, vector_index: dict[str, Any] | None = None) -> dict[str, Any]:
    initialize_memory_dirs(root)
    vector_index = vector_index or rebuild_vector_index(root)
    documents = list(vector_index["documents"].values())
    duplicates: list[dict[str, Any]] = []

    for index, left in enumerate(documents):
        for right in documents[index + 1 :]:
            if left["type"] != right["type"]:
                continue
            similarity = _cosine_similarity(left["embedding"], right["embedding"])
            if similarity < 0.9:
                continue
            duplicates.append(
                {
                    "left_path": left["path"],
                    "right_path": right["path"],
                    "type": left["type"],
                    "similarity": round(similarity, 4),
                }
            )
    payload = {"updated_at": now_iso(), "duplicate_count": len(duplicates), "pairs": duplicates[:40]}
    write_json(root / "memory" / "indexes" / "duplicate_candidates.json", payload)
    return payload


def build_phase3_memory_intelligence(root: Path = ROOT) -> dict[str, Any]:
    initialize_memory_dirs(root)
    decisions = promote_decisions(root)
    recall_index = rebuild_recall_index(root)
    vector_index = rebuild_vector_index(root, recall_index=recall_index)
    topic_clusters = build_topic_clusters(root, vector_index=vector_index)
    duplicates = detect_duplicate_candidates(root, vector_index=vector_index)
    return {
        "decision_count": len(decisions),
        "indexed_documents": recall_index["document_count"],
        "indexed_terms": recall_index["term_count"],
        "vector_documents": vector_index["document_count"],
        "topic_clusters": topic_clusters["cluster_count"],
        "duplicate_candidates": duplicates["duplicate_count"],
    }


def remember_text(text: str, topic: str = "manual", root: Path = ROOT) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Cannot remember empty text")
    initialize_memory_dirs(root)
    memory_id = f"note_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}_{uuid.uuid4().hex[:6]}_{_safe_id(text[:30])}"
    record = {
        "id": memory_id,
        "type": "manual_note",
        "topic": topic,
        "content": text,
        "created_at": now_iso(),
        "source": "telegram_or_local_command",
    }
    write_json(root / "memory" / "canonical" / "notes" / f"{memory_id}.json", record)
    append_raw_log("remember", text, topic=topic, importance="high", root=root)
    return record


def memory_status(root: Path = ROOT) -> dict:
    initialize_memory_dirs(root)
    base = root / "memory"
    current_documents = (
        len(list((base / "canonical" / "tools").glob("*.json")))
        + len(list((base / "canonical" / "repo_knowledge").glob("*.json")))
        + len(list((base / "canonical" / "notes").glob("*.json")))
        + len(list((base / "canonical" / "dreams").glob("*.json")))
        + len(list((base / "canonical" / "decisions").glob("*.json")))
    )
    index_path = base / "indexes" / "recall_index.json"
    vector_index_path = base / "indexes" / "vector_index.json"
    cluster_index_path = base / "indexes" / "topic_clusters.json"
    duplicate_index_path = base / "indexes" / "duplicate_candidates.json"
    recall_index: dict[str, Any] = {}
    vector_index: dict[str, Any] = {}
    topic_clusters: dict[str, Any] = {}
    duplicate_candidates: dict[str, Any] = {}
    if index_path.exists():
        try:
            recall_index = json.loads(index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            recall_index = {}
    for path, target in [
        (vector_index_path, "vector_index"),
        (cluster_index_path, "topic_clusters"),
        (duplicate_index_path, "duplicate_candidates"),
    ]:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if target == "vector_index":
            vector_index = payload
        elif target == "topic_clusters":
            topic_clusters = payload
        else:
            duplicate_candidates = payload
    if recall_index.get("document_count", 0) < current_documents or vector_index.get("document_count", 0) < current_documents:
        from engine.memory_intelligence import run_phase3_cycle

        phase3 = run_phase3_cycle(root)
        recall_index = json.loads(index_path.read_text(encoding="utf-8"))
        vector_index = json.loads(vector_index_path.read_text(encoding="utf-8"))
        topic_clusters = json.loads(cluster_index_path.read_text(encoding="utf-8"))
        duplicate_candidates = json.loads(duplicate_index_path.read_text(encoding="utf-8"))
    else:
        phase3 = None
    return {
        "tools": len(list((base / "canonical" / "tools").glob("*.json"))),
        "repos": len(list((base / "canonical" / "repo_knowledge").glob("*.json"))),
        "notes": len(list((base / "canonical" / "notes").glob("*.json"))),
        "dreams": len(list((base / "canonical" / "dreams").glob("*.json"))),
        "decisions": len(list((base / "canonical" / "decisions").glob("*.json"))),
        "raw_logs": len(list((base / "raw_logs").glob("*.log"))),
        "daily_summaries": len(list((base / "daily_summaries").glob("*.md"))),
        "topic_summaries": len(list((base / "topic_summaries").glob("*.md"))),
        "indexed_documents": recall_index.get("document_count", 0),
        "indexed_terms": recall_index.get("term_count", 0),
        "recall_index_updated_at": recall_index.get("updated_at"),
        "vector_documents": vector_index.get("document_count", phase3["vector_documents"] if phase3 else 0),
        "topic_clusters": topic_clusters.get("cluster_count", phase3["topic_clusters"] if phase3 else 0),
        "duplicate_candidates": duplicate_candidates.get("duplicate_count", phase3["duplicate_candidates"] if phase3 else 0),
    }


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\-\u0E00-\u0E7F]{3,}", text)]


def _extract_patterns(records: list[dict], raw_items: list[dict]) -> list[str]:
    counter: Counter[str] = Counter()
    for record in records:
        counter.update(_tokenize(json.dumps(record, ensure_ascii=False))[:80])
    for item in raw_items:
        counter.update(_tokenize(str(item.get("topic", ""))))
        counter.update(_tokenize(str(item.get("type", ""))))
    banned = {"https", "github", "com", "the", "and", "for", "with", "memory", "source", "path"}
    return [word for word, _ in counter.most_common(12) if word not in banned]


def run_dream_cycle(root: Path = ROOT, trigger: str = "manual") -> dict:
    """Run a deterministic v1 dream cycle: Light Sleep -> Deep Sleep -> REM."""
    initialize_memory_dirs(root)
    canonical = root / "memory" / "canonical"
    raw_items = _read_raw_log_items(root)
    tool_records = _read_json_files(canonical / "tools")
    repo_records = _read_json_files(canonical / "repo_knowledge")
    note_records = _read_json_files(canonical / "notes")

    light_sleep = {
        "high_importance_events": [item for item in raw_items if item.get("importance") == "high"][:20],
        "tool_count": len(tool_records),
        "repo_count": len(repo_records),
        "note_count": len(note_records),
    }
    promoted = {
        "tools": [item.get("tool_id") or item.get("name") for item in tool_records],
        "repos": [item.get("repo") for item in repo_records],
        "notes": [item.get("id") for item in note_records],
    }
    rem = {
        "patterns": _extract_patterns(tool_records + repo_records + note_records, raw_items),
        "insights": [
            "Use crawl4ai for web-to-Markdown ingestion before RAG/vector work.",
            "Use Reverse-Engineer style blueprinting after repo analysis when deeper architecture is needed.",
            "Use docmd after memory stabilizes to publish docs and llms.txt context.",
            "Use rtk only after core tests are green to reduce command-output token noise.",
        ],
        "next_actions": [
            "Keep /analyze repo outputs flowing into canonical repo knowledge.",
            "Review low-risk proposals before enabling real apply patches.",
            "Promote repeated manual notes into canonical decisions when they recur.",
        ],
    }
    dream_id = f"dream_{now_iso().replace(':', '').replace('-', '').replace('+', '_')}"
    dream = {
        "id": dream_id,
        "type": "dream_cycle_v1",
        "trigger": trigger,
        "created_at": now_iso(),
        "light_sleep": light_sleep,
        "deep_sleep": promoted,
        "rem": rem,
    }
    write_json(canonical / "dreams" / f"{dream_id}.json", dream)

    dreams_md = root / "memory" / "dreams.md"
    existing = dreams_md.read_text(encoding="utf-8") if dreams_md.exists() else "# HAX-Mind Dreams\n\n"
    entry = [
        f"## {dream_id}",
        f"- Trigger: {trigger}",
        f"- Tools: {light_sleep['tool_count']} | Repos: {light_sleep['repo_count']} | Notes: {light_sleep['note_count']}",
        f"- Patterns: {', '.join(rem['patterns']) or 'none'}",
        "- Next actions:",
        *[f"  - {action}" for action in rem["next_actions"]],
        "",
    ]
    write_text(dreams_md, existing.rstrip() + "\n\n" + "\n".join(entry))
    append_raw_log("dream_cycle", f"Dream cycle {dream_id} created by {trigger}", topic="dreaming", importance="high", root=root)
    from engine.memory_intelligence import run_phase3_cycle

    phase3 = run_phase3_cycle(root)
    dream["phase3_memory_intelligence"] = phase3
    write_json(canonical / "dreams" / f"{dream_id}.json", dream)
    return dream


def list_dreams(root: Path = ROOT, limit: int = 10) -> list[dict[str, Any]]:
    directory = _dreams_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_path"] = str(path.relative_to(root))
        records.append(payload)
    return records


def get_dream(dream_id: str, root: Path = ROOT) -> dict[str, Any]:
    path = _dreams_dir(root) / f"{dream_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Dream not found: {dream_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["_path"] = str(path.relative_to(root))
    return payload


def latest_dream(root: Path = ROOT) -> dict[str, Any] | None:
    dreams = list_dreams(root=root, limit=1)
    return dreams[0] if dreams else None


def explain_dream(dream: dict[str, Any] | None = None, *, root: Path = ROOT) -> str:
    dream = dream or latest_dream(root=root)
    if not dream:
        return "No dream exists yet. Run /dream now or analyze a repo first."

    rem = dream.get("rem", {})
    next_actions = rem.get("next_actions", [])[:3]
    insights = rem.get("insights", [])[:2]
    lines = [
        f"Dream: {dream['id']}",
        "A dream is a generated memory-reflection note, not a scheduled task or proposal.",
        f"Trigger: {dream.get('trigger', 'unknown')}",
        (
            "It summarizes patterns, insights, and recommended next actions from repo analysis, notes, tools, and raw logs."
        ),
        f"Patterns: {', '.join(rem.get('patterns', [])[:6]) or 'none'}",
    ]
    if insights:
        lines.append("Insights:")
        lines.extend(f"- {item}" for item in insights)
    if next_actions:
        lines.append("Recommended next actions:")
        lines.extend(f"- {item}" for item in next_actions)
    lines.append("If you want to act on it, turn it into a task or proposal.")
    return "\n".join(lines)


def recall(keyword: str, root: Path = ROOT, limit: int = 8) -> list[dict]:
    keyword = keyword.strip().lower()
    if not keyword:
        raise ValueError("Recall keyword is required")
    query_tokens = _tokenize(keyword)
    if not query_tokens:
        raise ValueError("Recall keyword is too short")

    index = rebuild_recall_index(root)
    vector_index = rebuild_vector_index(root, recall_index=index)
    documents: dict[str, dict[str, Any]] = index["documents"]
    terms: dict[str, dict[str, int]] = index["terms"]
    expanded_terms = _expand_query_terms(query_tokens, set(terms))
    adjacent_phrases = [f"{left} {right}" for left, right in zip(query_tokens, query_tokens[1:])]
    query_embedding = _embed_text(keyword)

    scored: dict[str, dict[str, Any]] = {}
    for query_token, matched_terms in expanded_terms.items():
        for matched_term in matched_terms:
            for doc_id, frequency in terms.get(matched_term, {}).items():
                bucket = scored.setdefault(doc_id, {"score": 0.0, "matched_terms": set(), "matched_query_terms": set()})
                bucket["score"] += 1.5 + min(frequency, 3) * 0.75
                bucket["matched_terms"].add(matched_term)
                bucket["matched_query_terms"].add(query_token)

    for doc_id, document in vector_index["documents"].items():
        similarity = _cosine_similarity(query_embedding, document["embedding"])
        if similarity <= 0:
            continue
        bucket = scored.setdefault(doc_id, {"score": 0.0, "matched_terms": set(), "matched_query_terms": set()})
        bucket["score"] += similarity * 6
        bucket["vector_similarity"] = round(similarity, 4)
        bucket["matched_terms"].update(document.get("top_terms", [])[:2])

    ranked: list[dict[str, Any]] = []
    for doc_id, data in scored.items():
        document = documents[doc_id]
        text = document["search_text"]
        lowered_text = text.lower()
        title_lower = document["title"].lower()
        coverage = len(data["matched_query_terms"]) / len(query_tokens)
        score = data["score"] + coverage * 5
        if keyword in lowered_text:
            score += 6
        score += sum(1.5 for term in data["matched_terms"] if term in title_lower)
        score += sum(1.25 for phrase in adjacent_phrases if phrase in lowered_text)
        matched_terms = sorted(data["matched_terms"])
        ranked.append(
            {
                "path": document["path"],
                "type": document["type"],
                "title": document["title"],
                "excerpt": _build_excerpt(text, matched_terms),
                "score": round(score, 3),
                "matched_terms": matched_terms,
                "coverage": round(coverage, 3),
                "vector_similarity": data.get("vector_similarity", 0.0),
            }
        )

    ranked.sort(key=lambda item: (-item["score"], -item["coverage"], item["title"]))
    return ranked[:limit]
