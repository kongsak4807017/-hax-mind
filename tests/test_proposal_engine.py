from engine.proposal_engine import archive_duplicate_pending_proposals, create_proposal, list_proposals


def _create_same_proposal(root):
    return create_proposal(
        title="Promote external tool repos into canonical memory",
        component="memory/tools",
        problem="tool knowledge is not yet promoted into canonical memory",
        root_cause="missing durable tool registry",
        solution="Run tool ingestion and review canonical memory.",
        expected_impact="Tool memory stays useful.",
        risk="low",
        files_to_modify=["engine/tool_registry.py"],
        tests_to_run=["tests/test_tool_registry.py"],
        rollback_plan="restore backup",
        metadata={"kind": "tool_memory"},
        root=root,
    )


def test_create_proposal_deduplicates_identical_pending_items(tmp_path):
    first = _create_same_proposal(tmp_path)
    second = _create_same_proposal(tmp_path)

    assert first["id"] == second["id"]
    proposals = list_proposals(limit=20, root=tmp_path)
    assert len(proposals) == 1
    assert proposals[0]["metadata"]["dedupe_hits"] == 1


def test_archive_duplicate_pending_proposals_marks_older_duplicates(tmp_path):
    first = _create_same_proposal(tmp_path)
    # Force a second distinct pending item by changing metadata slightly then aligning fingerprint later.
    second = create_proposal(
        title=first["title"],
        component=first["component"],
        problem=first["problem"],
        root_cause=first["root_cause"],
        solution=first["solution"],
        expected_impact=first["expected_impact"],
        risk=first["risk"],
        files_to_modify=first["files_to_modify"],
        tests_to_run=first["tests_to_run"],
        rollback_plan=first["rollback_plan"],
        metadata={"kind": "tool_memory", "extra": "x"},
        root=tmp_path,
    )
    second["fingerprint"] = first["fingerprint"]
    from engine.proposal_engine import save_proposal

    save_proposal(second, root=tmp_path)

    result = archive_duplicate_pending_proposals(root=tmp_path)

    assert result["archived_count"] == 1
    proposals = {proposal["id"]: proposal for proposal in list_proposals(limit=20, root=tmp_path)}
    archived = [proposal for proposal in proposals.values() if proposal["status"] == "archived_duplicate"]
    assert len(archived) == 1
