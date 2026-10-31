import sqlite3
import json
from collector import init_db, save_contributions
from signals import extract_signals_for_fact, SIGNAL_REGISTRY
from scoring import calculate_quality_score
from rules import run_window_audit, load_rules

print("\n" + "=" * 60)
print("DIAGNOSTIC EFFICIENCY PIPELINE TEST")
print("=" * 60)

# Check 1: Verify signals registered
print(f"[1] Registered Signals in signals.py: {list(SIGNAL_REGISTRY.keys())}")
assert "time_complexity" in SIGNAL_REGISTRY, "time_complexity signal is MISSING!"

# Check 2: Verify rules loaded from YAML
rules = load_rules()
rule_ids = [r["id"] for r in rules]
print(f"[2] Rules Loaded from rules.yaml: {rule_ids}")
assert "ASYMPTOTIC_INEFFICIENCY_REGRESSION" in rule_ids, "Rule is missing from rules.yaml!"

db_path = "audit.db"
init_db(db_path)

# A real git diff patch with nested loops O(N^2)
bad_algorithm_patch = """
@@ -10,6 +10,12 @@
+def process_orders(users, orders):
+    for user in users:
+        for order in orders:
+            if order['user_id'] == user['id']:
+                cache_copy = [o for o in orders]
+                print("Found match")
"""

mock_pr = [{
    "id": "tani770/Trustflag#99",
    "author": "inefficient_dev",
    "repo": "tani770/Trustflag",
    "pr_number": 99,
    "title": "Add order processing loop",
    "body": "Implements double loop searching across order items.",
    "additions": 8,
    "deletions": 0,
    "changed_files": 1,
    "created_at": "2026-11-01T12:00:00Z",
    "merged_at": "2026-11-01T12:10:00Z",
    "is_fork_target": False,
    "patch": bad_algorithm_patch
}]

# 3. Clean test records
with sqlite3.connect(db_path) as conn:
    conn.execute("DELETE FROM decisions WHERE username = 'inefficient_dev'")
    conn.execute("DELETE FROM scores WHERE contribution_id = 'tani770/Trustflag#99'")
    conn.execute("DELETE FROM evidence WHERE contribution_id = 'tani770/Trustflag#99'")
    conn.execute("DELETE FROM contributions WHERE id = 'tani770/Trustflag#99'")
    conn.commit()

# 4. Save PR Fact
save_contributions(mock_pr, db_path)

# 5. Extract Signals
signals = extract_signals_for_fact(mock_pr[0])
score = calculate_quality_score(signals)

print("\n[3] Extracted Signals for PR:")
for k, v in signals.items():
    print(f"    • {k:20s}: {v}")
print(f"    • Quality Score     : {score}")

assert signals["time_complexity"] >= 2.0, f"Expected time_complexity >= 2.0, got {signals['time_complexity']}"

# 6. Save Evidence & Scores
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    for sig_name, sig_val in signals.items():
        cursor.execute(
            "INSERT INTO evidence (contribution_id, signal_name, value) VALUES (?, ?, ?)",
            (mock_pr[0]["id"], sig_name, sig_val)
        )
    cursor.execute(
        "INSERT OR REPLACE INTO scores (contribution_id, score) VALUES (?, ?)",
        (mock_pr[0]["id"], score)
    )
    conn.commit()

# 7. Run Window Audit
print("\n[4] Running Window Audit Engine...")
decisions = run_window_audit("inefficient_dev", db_path)

print("\n[+] Decisions Output:")
print(json.dumps(decisions, indent=2))

assert len(decisions) >= 1, "Failed to flag asymptotic inefficiency!"
assert decisions[0]["rule_id"] == "ASYMPTOTIC_INEFFICIENCY_REGRESSION"
assert decisions[0]["flag"] == "FLAG_COMPLEXITY_REGRESSION"
print("\n" + "=" * 60)
print("SUCCESS: Inefficient O(N^2) code was caught and flagged!")
print("=" * 60 + "\n")
