import os
import sys
import asyncio
import sqlite3
import json
from typing import List, Dict, Any, Set
import httpx

from collector import init_db, fetch_user_contributions, save_contributions
from signals import extract_signals_for_fact
from scoring import calculate_quality_score
from rules import run_window_audit

DB_PATH = "audit.db"

def get_target_repo() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1].strip()
    return "tani770/Trustflag"

async def ingest_and_score(repo: str, token: str) -> List[Dict[str, Any]]:
    init_db(DB_PATH)
    
    timeout_config = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
    async with httpx.AsyncClient(timeout=timeout_config) as client:
        print(f"[*] Ingesting pull requests from GitHub repository: {repo}")
        facts = await fetch_user_contributions(repo, token, client)
        
    if not facts:
        print(f"[!] Zero pull requests found in '{repo}'. Nothing to process.")
        return []

    print(f"[+] Successfully fetched {len(facts)} contribution records.")
    save_contributions(facts, DB_PATH)

    print("[*] Computing signals and deterministic quality scores...")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for fact in facts:
            signals = extract_signals_for_fact(fact)
            score = calculate_quality_score(signals)

            cursor.execute("DELETE FROM evidence WHERE contribution_id = ?", (fact["id"],))
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

    return facts

def evaluate_contributors(facts: List[Dict[str, Any]]) -> None:
    unique_authors: Set[str] = {fact["author"] for fact in facts if fact.get("author")}
    print(f"[*] Auditing {len(unique_authors)} unique contributors through sliding window rules...")
    
    total_flags = 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for author in unique_authors:
            cursor.execute("DELETE FROM decisions WHERE username = ?", (author,))
            conn.commit()

            decisions = run_window_audit(author, DB_PATH)
            if decisions:
                total_flags += len(decisions)
                print(f"  [!] Contributor '{author}' FLAGGED: {len(decisions)} violation(s)")
                for d in decisions:
                    print(f"      - Rule: {d['rule_id']} | Action: {d['flag']} | Evidence IDs: {d['evidence_ids']}")
            else:
                print(f"  [✓] Contributor '{author}' CLEAN (Passed all rules)")

    print("\n" + "=" * 60)
    print(f"AUDIT SUMMARY: {len(facts)} PRs evaluated | {len(unique_authors)} Authors | {total_flags} Flags generated")
    print("=" * 60)

async def main():
    target_repo = get_target_repo()
    github_token = os.getenv("GITHUB_TOKEN", "").strip()

    if not github_token:
        print("[WARN] GITHUB_TOKEN environment variable not detected.")
        print("       Proceeding unauthenticated (Subject to 60 req/hr GitHub rate limit).")
    else:
        print("[INFO] Authenticated session active via GITHUB_TOKEN.")

    try:
        facts = await ingest_and_score(target_repo, github_token)
        if facts:
            evaluate_contributors(facts)
    except httpx.HTTPStatusError as exc:
        print(f"\n[ERROR] GitHub API returned status {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        print(f"\n[ERROR] Pipeline encountered an unexpected failure: {str(exc)}")

if __name__ == "__main__":
    asyncio.run(main())