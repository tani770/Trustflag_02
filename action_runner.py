import os
import sys
import json
import asyncio
import subprocess
import httpx

from scoring import calculate_quality_score
from rules import load_rules, check_operator
from bot import post_pr_audit_comment

async def run_ci_gate() -> None:
    print("\n" + "=" * 65)
    print("TRUSTFLAG AUTONOMOUS PR AUDIT RUNNER (ACCURACY ENGINE)")
    print("=" * 65)

    event_path = os.getenv("GITHUB_EVENT_PATH")
    github_token = os.getenv("GITHUB_TOKEN", "").strip()

    if not event_path or not os.path.exists(event_path):
        print("[!] No event payload found. Exiting safely.")
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
    base_ref = pr_data["base"]["ref"]

    print(f"[*] Auditing PR #{pr_number} by @{author} on {repo_name}")

    # 1. Identify changed Python files
    try:
        changed_proc = subprocess.run(
            ["git", "diff", "--name-only", f"origin/{base_ref}...HEAD"],
            capture_output=True, text=True, check=True
        )
        changed_files = [f.strip() for f in changed_proc.stdout.splitlines() if f.strip().endswith(".py")]
    except Exception:
        changed_files = [f for f in os.listdir(".") if f.endswith(".py") and not f.startswith(("test_", "action_runner", "bot", "collector", "rules", "signals", "scoring", "api"))]

    print(f"[+] Python files to verify: {changed_files}")

    # 2. Accuracy Verification Loop
    total_checks = 0
    passed_checks = 0
    syntax_valid = 1.0

    for file_path in changed_files:
        if not os.path.exists(file_path):
            continue

        # Check A: Syntax Compilation Accuracy
        total_checks += 1
        with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
            source_code = fp.read()

        try:
            compile(source_code, file_path, "exec")
            passed_checks += 1
            print(f"  • [PASS] Syntax compilation for '{file_path}'")
        except Exception as e:
            syntax_valid = 0.0
            print(f"  • [FAIL] Syntax compilation error in '{file_path}': {e}")

        # Check B: Functional Execution Accuracy (Runs standalone logic/assertions)
        total_checks += 1
        run_proc = subprocess.run([sys.executable, file_path], capture_output=True, text=True)
        if run_proc.returncode == 0:
            passed_checks += 1
            print(f"  • [PASS] Functional runtime execution for '{file_path}'")
        else:
            print(f"  • [FAIL] Runtime error in '{file_path}': {run_proc.stderr.strip()[:200]}")

    # Check C: Discover and Run Automated Unit Tests (pytest / unittest)
    test_files = [f for f in os.listdir(".") if f.startswith("test_") and f.endswith(".py")]
    for tf in test_files:
        total_checks += 1
        t_proc = subprocess.run([sys.executable, "-m", "unittest", tf], capture_output=True, text=True)
        if t_proc.returncode == 0:
            passed_checks += 1
            print(f"  • [PASS] Test suite '{tf}' passed 100%")
        else:
            print(f"  • [FAIL] Test suite '{tf}' encountered failures")

    # 3. Calculate Strict Accuracy Ratio
    accuracy = (passed_checks / total_checks) if total_checks > 0 else 1.0
    signals = {
        "accuracy": accuracy,
        "syntax_valid": syntax_valid,
        "tests_passed": float(passed_checks),
        "tests_total": float(total_checks)
    }

    score = calculate_quality_score(signals)
    signals["score"] = score

    print("\n--- Final Evaluated Accuracy ---")
    print(f" • Accuracy Percentage : {accuracy * 100.0:.2f}%")
    print(f" • Checks Passed       : {passed_checks}/{total_checks}")
    print(f" • Quality Score       : {score:.4f} (Required: 1.0000)")

    # 4. Evaluate Rules (Requires 100% Accuracy)
    rules = load_rules("rules.yaml")
    triggered_violations = []

    for rule in rules:
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

    # Hard assert: If accuracy is not 100%, trigger violation
    if accuracy < 1.0 and not any(v["rule_id"] == "REQUIRE_100_PERCENT_ACCURACY" for v in triggered_violations):
        triggered_violations.append({
            "rule_id": "REQUIRE_100_PERCENT_ACCURACY",
            "flag": f"FLAG_INACCURATE_CODE (Accuracy: {accuracy * 100.0:.1f}% < 100.0%)"
        })

    # 5. Comment on PR Thread
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

    # 6. CI Gate Enforcement (100% or FAIL)
    if accuracy < 1.0 or triggered_violations:
        print(f"\n[❌ GATE REJECTED] Code is NOT 100% accurate ({accuracy * 100.0:.1f}%).")
        for v in triggered_violations:
            print(f"   - {v['rule_id']}: {v['flag']}")
        print("\nBlocking PR merge: Only 100% accurate code is approved.")
        sys.exit(1)
    else:
        print(f"\n[✅ GATE PASSED] Code verified 100% accurate. Approved for merge.")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(run_ci_gate())
