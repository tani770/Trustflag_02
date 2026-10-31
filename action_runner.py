import os
import sys
import json
import asyncio
import subprocess
import httpx

from signals import extract_signals_for_fact, compute_ast_complexity
from scoring import calculate_quality_score
from rules import load_rules, check_operator
from bot import post_pr_audit_comment

async def run_ci_gate():
    print("\n" + "=" * 60)
    print("TRUSTFLAG AUTONOMOUS PR AUDIT RUNNER (DISK AST ENGINE)")
    print("=" * 60)

    event_path = os.getenv("GITHUB_EVENT_PATH")
    github_token = os.getenv("GITHUB_TOKEN")

    if not event_path or not os.path.exists(event_path):
        print("[ERROR] GITHUB_EVENT_PATH not found.")
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
    base_ref = pr_data["base"]["ref"]  # usually 'main'

    print(f"[*] Auditing PR #{pr_number} by @{author} on {repo_name}")

    # 1. Detect all modified/added Python files on disk via git
    try:
        changed_files_proc = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
            capture_output=True, text=True, check=True
        )
        changed_files = [f.strip() for f in changed_files_proc.stdout.splitlines() if f.strip().endswith(".py")]
    except Exception as e:
        print(f"[WARN] Git diff command failed ({e}). Scanning repository for py files...")
        changed_files = [f for f in os.listdir(".") if f.endswith(".py") and not f.startswith(("test_", "action_runner", "bot", "collector", "rules", "signals", "scoring", "api"))]

    print(f"[+] Identified modified Python files to audit: {changed_files}")

    # 2. Read file contents directly from disk and find maximum complexity
    max_time_complexity = 0.0
    max_space_complexity = 0.0
    combined_code = []

    for file_path in changed_files:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
                combined_code.append(content)
                t_order, s_order = compute_ast_complexity(content)
                print(f"  • Scanned '{file_path}' -> Time: O(N^{int(t_order)}), Space: O(N^{int(s_order)})")
                max_time_complexity = max(max_time_complexity, t_order)
                max_space_complexity = max(max_space_complexity, s_order)

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
        "patch": "\n".join(combined_code)
    }

    # 4. Extract Signals & Quality Score
    signals = extract_signals_for_fact(fact)
    # Overwrite with true disk AST analysis
    signals["time_complexity"] = max_time_complexity
    signals["space_complexity"] = max_space_complexity

    score = calculate_quality_score(signals)
    signals["score"] = score

    print("\n--- Final Evaluated PR Metrics ---")
    print(f" • Time Complexity   : O(N^{int(signals['time_complexity'])})")
    print(f" • Space Complexity  : O(N^{int(signals['space_complexity'])})")
    print(f" • Diff Churn / File : {signals.get('churn_per_file', 0)} lines")
    print(f" • Title Entropy     : {signals.get('title_entropy', 0):.2f} bits")
    print(f" • Quality Score     : {score}")

    # 5. Evaluate Rules from rules.yaml
    rules = load_rules("rules.yaml")
    triggered_violations = []

    for rule in rules:
        if any(c["signal"] == "duration_seconds" for c in rule["conditions"]) and signals.get("duration_seconds", -1.0) < 0:
            continue

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

    # 6. Post Audit Comment to PR Thread
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
        print("\nBlocking PR merge due to O(N^2)+ complexity regression.")
        sys.exit(1)
    else:
        print("\n[✅ GATE PASSED] Code meets complexity and quality thresholds.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_ci_gate())
