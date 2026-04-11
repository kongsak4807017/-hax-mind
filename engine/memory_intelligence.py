from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from engine.dreaming import rebuild_recall_index, recall as lexical_recall
from engine.memory_store import initialize_memory_dirs, write_json, write_text
from engine.utils import ROOT, now_iso

VECTOR_DIMENSIONS = 128


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()[:80] or "item"


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9_\-\u0E00-\u0E7F]{3,}", text)]


def _canonical_dirs(root: Path, include_decisions: bool = True) -> list[Path]:
    dirs = [
        root / "memory" / "canonical" / "tools",
        root / "memory" / "canonical" / "repo_knowledge",
        root / "memory" / "canonical" / "notes",
        root / "memory" / "canonical" / "dreams",
    ]
    if include_decisions:
        dirs.append(root / "memory" / "canonical" / "decisions")
    return dirs


def _document_title(payload: dict[str, Any], path: Path) -> str:
    return payload.get("name") or payload.get("repo") or payload.get("title") or payload.get("id") or path.stem


def _document_type(payload: dict[str, Any], path: Path) -> str:
    return payload.get("type") or payload.get("role") or path.parent.name


def _document_text(payload: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", json.dumps(payload, ensure_ascii=False)).strip()


def _hash_bucket(token: str, dimensions: int = VECTOR_DIMENSIONS) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % dimensions


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _embed_text(text: str, dimensions: int = VECTOR_DIMENSIONS) -> list[float]:
    counter = Counter(_tokenize(text))
    vector = [0.0] * dimensions
    for token, frequency in counter.items():
        vector[_hash_bucket(token, dimensions)] += 1.0 + math.log1p(frequency)
    return _normalize(vector)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _top_terms(text: str, limit: int = 8) -> list[str]:
    banned = {"https", "github", "memory", "source", "path", "content", "created_at", "updated_at"}
    counts = Counter(token for token in _tokenize(text) if token not in banned)
    return [token for token, _ in counts.most_common(limit)]


def _excerpt(search_text: str, query: str, radius: int = 140) -> str:
    lowered = search_text.lower()
    position = lowered.find(query.lower())
    if position < 0:
        for token in _tokenize(query):
            position = lowered.find(token)
            if position >= 0:
                break
    if position < 0:
        position = 0
    excerpt = search_text[max(0, position - radius) : position + radius]
    return re.sub(r"\s+", " ", excerpt).strip()[:320]


def _load_documents(root: Path, include_decisions: bool = True) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for directory in _canonical_dirs(root, include_decisions=include_decisions):
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            search_text = _document_text(payload)
            documents.append(
                {
                    "path": str(path.relative_to(root)),
                    "title": _document_title(payload, path),
                    "type": _document_type(payload, path),
                    "search_text": search_text,
                    "top_terms": _top_terms(search_text),
                    "vector": _embed_text(search_text),
                }
            )
    return documents


def rebuild_vector_index(root: Path = ROOT) -> dict[str, Any]:
    initialize_memory_dirs(root)
    documents = _load_documents(root, include_decisions=True)
    index = {
        "updated_at": now_iso(),
        "dimensions": VECTOR_DIMENSIONS,
        "document_count": len(documents),
        "documents": documents,
    }
    write_json(root / "memory" / "indexes" / "vector_index.json", index)
    return index


def vector_search(query: str, root: Path = ROOT, limit: int = 8, min_score: float = 0.12) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise ValueError("Vector search query is required")
    index = rebuild_vector_index(root)
    query_vector = _embed_text(query)
    results: list[dict[str, Any]] = []
    for document in index["documents"]:
        score = _cosine_similarity(query_vector, document["vector"])
        if score < min_score:
            continue
        results.append(
            {
                "path": document["path"],
                "title": document["title"],
                "type": document["type"],
                "score": round(score, 4),
                "top_terms": document["top_terms"],
                "excerpt": _excerpt(document["search_text"], query),
            }
        )
    results.sort(key=lambda item: (-item["score"], item["title"]))
    return results[:limit]


def hybrid_recall(query: str, root: Path = ROOT, limit: int = 8) -> list[dict[str, Any]]:
    lexical = lexical_recall(query, root=root, limit=limit * 2)
    vector = vector_search(query, root=root, limit=limit * 2)
    lexical_max = max((item["score"] for item in lexical), default=1.0)
    vector_max = max((item["score"] for item in vector), default=1.0)
    combined: dict[str, dict[str, Any]] = {}

    for item in lexical:
        bucket = combined.setdefault(
            item["path"],
            {
                "path": item["path"],
                "title": item["title"],
                "type": item["type"],
                "excerpt": item["excerpt"],
                "lexical_score": 0.0,
                "vector_score": 0.0,
                "matched_terms": list(item.get("matched_terms", [])),
                "top_terms": [],
            },
        )
        bucket["lexical_score"] = item["score"] / lexical_max if lexical_max else item["score"]
        bucket["matched_terms"] = list(item.get("matched_terms", []))
        bucket["excerpt"] = item["excerpt"]

    for item in vector:
        bucket = combined.setdefault(
            item["path"],
            {
                "path": item["path"],
                "title": item["title"],
                "type": item["type"],
                "excerpt": item["excerpt"],
                "lexical_score": 0.0,
                "vector_score": 0.0,
                "matched_terms": [],
                "top_terms": item.get("top_terms", []),
            },
        )
        bucket["vector_score"] = item["score"] / vector_max if vector_max else item["score"]
        bucket["top_terms"] = item.get("top_terms", [])
        if not bucket["excerpt"]:
            bucket["excerpt"] = item["excerpt"]

    results = []
    for item in combined.values():
        item["score"] = round(item["lexical_score"] + item["vector_score"], 4)
        results.append(item)
    results.sort(key=lambda item: (-item["score"], -item["lexical_score"], item["title"]))
    return results[:limit]


def _average_vector(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return [0.0] * VECTOR_DIMENSIONS
    avg = [0.0] * len(vectors[0])
    for vector in vectors:
        for index, value in enumerate(vector):
            avg[index] += value
    return _normalize([value / len(vectors) for value in avg])


def cluster_topics(root: Path = ROOT, threshold: float = 0.24, min_cluster_size: int = 2) -> dict[str, Any]:
    index = rebuild_vector_index(root)
    clusters: list[dict[str, Any]] = []

    for document in index["documents"]:
        placed = False
        for cluster in clusters:
            score = _cosine_similarity(document["vector"], cluster["centroid"])
            if score >= threshold:
                cluster["members"].append(document)
                cluster["centroid"] = _average_vector([member["vector"] for member in cluster["members"]])
                placed = True
                break
        if not placed:
            clusters.append({"members": [document], "centroid": document["vector"]})

    rendered_clusters: list[dict[str, Any]] = []
    for position, cluster in enumerate(clusters, start=1):
        if len(cluster["members"]) < min_cluster_size:
            continue
        terms = Counter()
        for member in cluster["members"]:
            terms.update(member["top_terms"])
        label_terms = [term for term, _ in terms.most_common(4)]
        rendered_clusters.append(
            {
                "id": f"cluster_{position:02d}",
                "label": " / ".join(label_terms[:3]) or f"cluster_{position:02d}",
                "member_count": len(cluster["members"]),
                "members": [
                    {"path": member["path"], "title": member["title"], "type": member["type"]}
                    for member in cluster["members"]
                ],
                "top_terms": label_terms,
            }
        )

    payload = {"updated_at": now_iso(), "cluster_count": len(rendered_clusters), "clusters": rendered_clusters}
    write_json(root / "memory" / "indexes" / "topic_clusters.json", payload)
    lines = ["# Topic Clusters", "", f"Updated: {payload['updated_at']}", ""]
    if not rendered_clusters:
        lines.append("No topic clusters yet.")
    for cluster in rendered_clusters:
        lines.extend(
            [
                f"## {cluster['label']}",
                f"- Members: {cluster['member_count']}",
                f"- Terms: {', '.join(cluster['top_terms'])}",
                *[f"- {member['title']} | {member['path']}" for member in cluster["members"]],
                "",
            ]
        )
    write_text(root / "memory" / "topic_summaries" / "topic_clusters.md", "\n".join(lines).rstrip() + "\n")
    return payload


def _decision_evidence(root: Path) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    notes_dir = root / "memory" / "canonical" / "notes"
    for path in sorted(notes_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        evidence.append(
            {
                "id": payload.get("id", path.stem),
                "path": str(path.relative_to(root)),
                "text": payload.get("content", ""),
                "title": payload.get("id", path.stem),
                "type": "note",
            }
        )

    dreams_dir = root / "memory" / "canonical" / "dreams"
    for path in sorted(dreams_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for index, action in enumerate(payload.get("rem", {}).get("next_actions", []), start=1):
            evidence.append(
                {
                    "id": f"{payload.get('id', path.stem)}_action_{index}",
                    "path": str(path.relative_to(root)),
                    "text": action,
                    "title": payload.get("id", path.stem),
                    "type": "dream_action",
                }
            )
    return evidence


def promote_decisions(root: Path = ROOT, threshold: float = 0.3, min_evidence: int = 2) -> list[dict[str, Any]]:
    initialize_memory_dirs(root)
    evidence = _decision_evidence(root)
    items = [
        {
            **item,
            "vector": _embed_text(item["text"]),
            "top_terms": _top_terms(item["text"], limit=6),
        }
        for item in evidence
        if item["text"].strip()
    ]
    clusters: list[list[dict[str, Any]]] = []
    for item in items:
        placed = False
        for cluster in clusters:
            centroid = _average_vector([entry["vector"] for entry in cluster])
            if _cosine_similarity(item["vector"], centroid) >= threshold:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])

    decisions: list[dict[str, Any]] = []
    decisions_dir = root / "memory" / "canonical" / "decisions"
    for cluster in clusters:
        if len(cluster) < min_evidence:
            continue
        terms = Counter()
        for item in cluster:
            terms.update(item["top_terms"])
        label_terms = [term for term, _ in terms.most_common(4)]
        decision_id = f"decision_{_safe_id('_'.join(label_terms[:3]))}"
        decision = {
            "id": decision_id,
            "title": " / ".join(label_terms[:3]) or decision_id,
            "summary": cluster[0]["text"][:220],
            "created_at": now_iso(),
            "confidence": round(min(0.99, 0.45 + len(cluster) * 0.1), 2),
            "evidence_count": len(cluster),
            "evidence": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "path": item["path"],
                    "type": item["type"],
                    "text": item["text"][:220],
                }
                for item in cluster
            ],
            "top_terms": label_terms,
        }
        write_json(decisions_dir / f"{decision_id}.json", decision)
        decisions.append(decision)

    summary_lines = ["# Promoted Decisions", "", f"Updated: {now_iso()}", ""]
    if not decisions:
        summary_lines.append("No recurring decisions found yet.")
    for decision in decisions:
        summary_lines.extend(
            [
                f"## {decision['title']}",
                f"- Confidence: {decision['confidence']}",
                f"- Evidence count: {decision['evidence_count']}",
                f"- Summary: {decision['summary']}",
                *[f"- Evidence: {item['title']} | {item['path']}" for item in decision["evidence"]],
                "",
            ]
        )
    write_text(root / "memory" / "topic_summaries" / "decisions.md", "\n".join(summary_lines).rstrip() + "\n")
    return decisions


def list_decisions(root: Path = ROOT, limit: int = 10) -> list[dict[str, Any]]:
    decisions_dir = root / "memory" / "canonical" / "decisions"
    decisions_dir.mkdir(parents=True, exist_ok=True)
    decisions = []
    for path in sorted(decisions_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        decisions.append(json.loads(path.read_text(encoding="utf-8")))
    return decisions


def list_topic_clusters(root: Path = ROOT, limit: int = 10) -> list[dict[str, Any]]:
    path = root / "memory" / "indexes" / "topic_clusters.json"
    if not path.exists():
        return cluster_topics(root=root).get("clusters", [])[:limit]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("clusters", [])[:limit]


def detect_duplicate_memories(root: Path = ROOT, threshold: float = 0.92) -> list[dict[str, Any]]:
    documents = [item for item in _load_documents(root, include_decisions=False) if item["type"] in {"manual_note", "dream_cycle_v1"}]
    duplicates: list[dict[str, Any]] = []
    for left_index, left in enumerate(documents):
        for right in documents[left_index + 1 :]:
            score = _cosine_similarity(left["vector"], right["vector"])
            if score < threshold:
                continue
            duplicates.append(
                {
                    "left_path": left["path"],
                    "right_path": right["path"],
                    "score": round(score, 4),
                    "left_title": left["title"],
                    "right_title": right["title"],
                }
            )
    write_json(
        root / "memory" / "indexes" / "duplicate_candidates.json",
        {"updated_at": now_iso(), "duplicate_count": len(duplicates), "duplicates": duplicates},
    )
    return duplicates


def run_phase3_cycle(root: Path = ROOT) -> dict[str, Any]:
    recall_index = rebuild_recall_index(root)
    vector_index = rebuild_vector_index(root)
    clusters = cluster_topics(root)
    decisions = promote_decisions(root)
    duplicates = detect_duplicate_memories(root)
    return {
        "updated_at": now_iso(),
        "indexed_documents": recall_index["document_count"],
        "indexed_terms": recall_index["term_count"],
        "vector_documents": vector_index["document_count"],
        "topic_clusters": clusters["cluster_count"],
        "decisions": len(decisions),
        "duplicate_candidates": len(duplicates),
    }
