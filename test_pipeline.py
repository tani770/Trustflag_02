import sqlite3
import json
from collector import init_db, save_contributions
from signals import extract_signals_for_fact
from scoring import calculate_quality_score
from rules import run_window_audit

def run_test():
    db_path = "audit.db"

    # 1. Initialize schema
    init_db(db_path)

    # Clean previous test artifacts so the script is 100% repeatable
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM decisions WHERE username = 'sybil_user'")
        cursor.execute("DELETE FROM scores WHERE contribution_id LIKE 'octocat/Hello-World%'")
        cursor.execute("DELETE FROM evidence WHERE contribution_id LIKE 'octocat/Hello-World%'")
        cursor.execute("DELETE FROM contributions WHERE author = 'sybil_user'")
        conn.commit()

    # 2. Fabricate raw contribution facts (3 burst PRs within 30 minutes)
    mock_facts = [
        {
            "id": "octocat/Hello-World#1",
            "author": "sybil_user",
            "repo": "octocat/Hello-World",
            "pr_number": 1,
            "title": "fix",
            "body": "none",
            "additions": 1,
            "deletions": 1,
            "changed_files": 1,
            "created_at": "2026-03-01T10:00:00Z",
            "merged_at": "2026-03-01T10:01:00Z",
            "is_fork_target": False
        },
        {
            "id": "octocat/Hello-World#2",
            "author": "sybil_user",
            "repo": "octocat/Hello-World",
            "pr_number": 2,
            "title": "update",
            "body": "short",
            "additions": 2,
            "deletions": 0,
            "changed_files": 1,
            "created_at": "2026-03-01T10:15:00Z",
            "merged_at": "2026-03-01T10:16:00Z",
            "is_fork_target": False
        },
        {
            "id": "octocat/Hello-World#3",
            "author": "sybil_user",
            "repo": "octocat/Hello-World",
            "pr_number": 3,
            "title": "typo",
            "body": "fixes",
            "additions": 1,
            "deletions": 1,
            "changed_files": 1,
            "created_at": "2026-03-01T10:30:00Z",
            "merged_at": "2026-03-01T10:31:00Z",
            "is_fork_target": False
        }
    ]

    # 3. Save raw facts into the contributions table
    save_contributions(mock_facts, db_path)

    # 4. Extract signals and persist evidence & quality scores
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        for fact in mock_facts:
            signals = extract_signals_for_fact(fact)
            score = calculate_quality_score(signals)

            for sig_name, sig_val in signals.items():
                cursor.execute(
                    "INSERT INTO evidence (contribution_id, signal_name, value) VALUES (?, ?, ?)",
                    (fact["id"], sig_name, sig_val)
                )

            cursor.execute(
                "INSERT OR REPLACE INTO scores (contribution_id, score) VALUES (?, ?)",
                (fact["id"], score)
            )
        conn.commit()

    # 5. Run the window rules engine
    decisions = run_window_audit("sybil_user", db_path)

    # 6. Verify assertions
    print("\n[+] Pipeline run complete.")
    print(f"[+] Decisions count: {len(decisions)}")
    print(f"[+] Decision Output:\n{json.dumps(decisions, indent=2)}")

    assert len(decisions) >= 1, "Audit failed to catch burst spam!"
    assert decisions[0]["rule_id"] == "BURST_LOW_EFFORT"
    assert len(decisions[0]["evidence_ids"]) > 0
    print("\n Verification Successful: Evidentiary trail generated cleanly.")

if __name__ == "__main__":
    run_test()