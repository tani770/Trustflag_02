import os
import sys
import json
import asyncio
from typing import Dict, Any, List
import httpx

from signals import extract_signals_for_fact
from scoring import calculate_quality_score
from rules import load_rules, check_operator
from bot import post_pr_audit_comment

async def run_ci_gate() -> None:
    print("\n" + "=" * 60)
    print("TRUSTFLAG AUTONOMOUS PR AUDIT RUNNER")
    print("=" * 60)

    # 1. Ingest GitHub Actions environment context
    event_path = os.getenv("GITHUB_EVENT_PATH")
    github_token = os.getenv("GITHUB_TOKEN", "").strip()

    if not event_path or not os.path.exists(event_path):
        print("[!] GITHUB_EVENT_PATH not detected. Exiting safely.")
        sys.exit(0)

    with open(event_path, "r", encoding="utf-8") as f:
        event_payload = json.load(f)

    if "pull_request" not in event_payload:
        print("[!] Non-PR event triggered. Skipping.")
        sys.exit(0)

    pr_data = event_payload["pull_request"]
    repo_name = event_payload["repository"]["full_name"]
    pr_number = pr_data["number"]
    author = pr_data["user"]["login"]

    print(f"[*] Auditing PR #{pr_number} by @{author} on {repo_name}")

    # 2. Extract immutable raw fact (Zero AST / Zero Complexity dependencies)
    fact: Dict[str, Any] = {
        "id": f"{repo_name}#{pr_number}",
        "author": author,
        "repo": repo_name,
        "pr_number": pr_number,
        "title": pr_data.get("title") or "",
        "body": pr_data.get("body") or "",
        "additions": pr_data.get("additions", 0),
        "deletions": pr_data.get("deletions", 0),
        "changed_files": pr_data.get("changed_files", 0),
        "created_at": pr_data.get("created_at", ""),
        "merged_at": pr_data.get("merged_at"),
        "is_fork_target": bool(event_payload.get("repository", {}).get("fork", False))
    }

    # 3. Extract baseline signals & compute quality score
    signals = extract_signals_for_fact(fact)
    score = calculate_quality_score(signals)
    signals["score"] = score

    print("\n--- PR Quality & Effort Metrics ---")
    print(f" • Diff Churn / File : {signals.get('churn_per_file', 0.0):.1f} lines")
    print(f" • Commit Entropy    : {signals.get('title_entropy', 0.0):.2f} bits")
    print(f" • Body Length       : {int(signals.get('body_length', 0.0))} chars")
    print(f" • Quality Score     : {score:.4f} / 1.0000")

    # 4. Evaluate single-PR gate rules
    rules = load_rules("rules.yaml")
    triggered_violations: List[Dict[str, Any]] = []

    for rule in rules:
        # Bypass multi-event temporal window rules (belongs to historical DB engine)
        if rule.get("min_event_count", 1) > 1:
            continue

        # Bypass post-merge rules on open pull requests
        if any(c["signal"] == "duration_seconds" for c in rule.get("conditions", [])) and signals.get("duration_seconds", -1.0) < 0:
            continue

        # Bypass complexity-specific rules
        if any(c["signal"] in ["time_complexity", "space_complexity"] for c in rule.get("conditions", [])):
            continue

        all_passed = True
        for cond in rule.get("conditions", []):
            sig_name = cond["signal"]
            val = signals.get(sig_name, 0.0)
            if not check_operator(val, cond["operator"], cond["threshold"]):
                all_passed = False
                break

        if all_passed:
            triggered_violations.append({
                "rule_id": rule["id"],
                "flag": rule["action"]
            })

    # 5. Provide diagnostic comment on PR thread
    if github_token:
        async with httpx.AsyncClient() as client:
            await post_pr_audit_comment(
                repo=repo_name,
                pr_number=pr_number,
                author=author,
                score=score,
                decisions=triggered_violations,
                signals=signals,
                appeal_url=f"https://github.com/{repo_name}/issues/{pr_number}",
                token=github_token,
                client=client
            )

    # 6. CI Enforcement Decision
    if triggered_violations:
        print(f"\n[❌ GATE REJECTED] Found {len(triggered_violations)} violation(s):")
        for v in triggered_violations:
            print(f"   - {v['rule_id']} ({v['flag']})")
        print("\nBlocking PR merge due to quality violations.")
        sys.exit(1)
    else:
        print("\n[✅ GATE PASSED] Pull request satisfies quality baseline.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_ci_gate())