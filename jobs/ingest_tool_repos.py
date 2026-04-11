from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.github_ingestor import ingest_all_tools

if __name__ == "__main__":
    records = ingest_all_tools()
    print(f"Ingested {len(records)} tools:")
    for record in records:
        print(f"- {record['tool_id']}: {record['name']} -> {record['role']}")
