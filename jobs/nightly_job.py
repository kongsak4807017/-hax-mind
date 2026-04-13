from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.memory_analyzer import summarize_today
from engine.self_improvement_engine import generate_improvement_proposal
from engine.auto_learning import nightly_learning_cycle

if __name__ == "__main__":
    summarize_today()
    proposal = generate_improvement_proposal()
    print(f"Nightly proposal created: {proposal['id']}")
    
    # Run auto-learning cycle
    print("Running auto-learning cycle...")
    learning_result = nightly_learning_cycle()
    print(f"Auto-learning complete: {len(learning_result['proposals_created'])} proposals created")
    if learning_result['proposals_created']:
        for p in learning_result['proposals_created']:
            print(f"  - {p.get('proposal_id', 'unknown')}")
