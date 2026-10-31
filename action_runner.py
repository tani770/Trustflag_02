import os
import sys
import json
import asyncio
import httpx

from signals import extract_signals_for_fact
from scoring import calculate_quality_score
from rules import load_rules, check_operator
from bot import post_pr_audit_comment

async def run_ci_gate():
    print("\n" + "=" * 60)
    print("TRUSTFLAG AUTONOMOUS PR AUDIT RUNNER")
    print("=" * 60)

    # 1. Read GitHub Actions environment variables
    event_path = os.getenv("GITHUB_EVENT_PATH")
    github_token = os.getenv("GITHUB_TOKEN")
    
    if not event_path or not os.path.exists(event_path):
        print("[ERROR] GITHUB_EVENT_PATH not found. This script must run inside GitHub Actions.")
        sys.exit(1)

    with open(event_path, "r") as f:
        event_payload = json.load(f)

    if "pull_request" not in event_payload:
        print("[!] Not a pull request event. Skipping.")
        sys.exit(0)

    pr_data = event_payload["pull_request"]
    repo_name = event_payload["repository"]["full_name"]
    pr_number = pr_data["number"]
    author = pr_data["user"]["login"]
    diff_url = pr_data["diff_url"]

    print(f"[*] Auditing PR #{pr_number} by @{author} on {repo_name}")

    # 2. Fetch raw patch directly from GitHub's diff URL
    headers = {"Authorization": f"Bearer {github_token}"} if github_token else {}
    async with httpx.AsyncClient() as client:
        diff_resp = await client.get(diff_url, headers=headers)
        raw_patch = diff_resp.text if diff_resp.status_code == 200 else ""

    # 3. Construct Fact
    fact = {
        "id": f"{repo_name}#{pr_number}",
        "author": author,
        "repo": repo_name,
        "pr_number": pr_number,
        "title": pr_data.get("title") or "",
        "body": pr_data.get("body") or "",
        "additions": pr_data.get("additions", 0),
        "deletions": pr_data.get("deletions", 0),
        "changed_files": pr_data.get("changed_files", 0),
        "patch": raw_patch
    }

    # 4. Extract Pure Signals & Algorithmic Complexity
    signals = extract_signals_for_fact(fact)
    score = calculate_quality_score(signals)

    print("\n--- Extracted PR Metrics ---")
    print(f" • Time Complexity   : O(N^{int(signals.get('time_complexity', 0))})")
    print(f" • Space Complexity  : O(N^{int(signals.get('space_complexity', 0))})")
    print(f" • Diff Churn / File : {signals.get('churn_per_file', 0)} lines")
    print(f" • Title Entropy     : {signals.get('title_entropy', 0):.2f} bits")
    print(f" • Quality Score     : {score}")

    # 5. Evaluate Single-Event Rules from rules.yaml
    rules = load_rules("rules.yaml")
    triggered_violations = []

    for rule in rules:
        all_passed = True
        for cond in rule["conditions"]:
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

    # 6. Post Audit Comment to GitHub PR Thread
    async with httpx.AsyncClient() as client:
        await post_pr_audit_comment(
            repo=repo_name,
            pr_number=pr_number,
            author=author,
            score=score,
            decisions=triggered_violations,
            signals=signals,
            appeal_url=f"https://github.com/{repo_name}/issues/{pr_number}",
            token=github_token or "",
            client=client
        )

    # 7. CI Pass / Fail Gate
    if triggered_violations:
        print(f"\n[❌ GATE REJECTED] Found {len(triggered_violations)} violation(s):")
        for v in triggered_violations:
            print(f"   - {v['rule_id']} ({v['flag']})")
        print("\nBlocking PR merge due to quality/efficiency regression.")
        sys.exit(1)  # Exits non-zero to fail the GitHub Actions check
    else:
        print("\n[✅ GATE PASSED] Code meets complexity and quality thresholds.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_ci_gate())
