from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.memory_analyzer import summarize_today
from engine.self_improvement_engine import generate_improvement_proposal

if __name__ == "__main__":
    summarize_today()
    proposal = generate_improvement_proposal()
    print(f"Nightly proposal created: {proposal['id']}")
