import yaml
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple

def load_rules(config_path: str = "rules.yaml") -> List[Dict[str, Any]]:
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("window_rules", [])

def check_operator(val: float, operator: str, threshold: float) -> bool:
    if operator == "lt":
        return val < threshold
    elif operator == "lte":
        return val <= threshold
    elif operator == "gt":
        return val > threshold
    elif operator == "gte":
        return val >= threshold
    elif operator == "eq":
        return val == threshold
    return False

def run_window_audit(author: str, db_path: str = "audit.db") -> List[Dict[str, Any]]:
    rules = load_rules()
    decisions = []
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 1. Fetch contributions ordered chronologically
        cursor.execute("""
            SELECT c.*, s.score 
            FROM contributions c
            LEFT JOIN scores s ON c.id = s.contribution_id
            WHERE c.author = ?
            ORDER BY c.created_at ASC
        """, (author,))
        contribs = [dict(row) for row in cursor.fetchall()]
        
        if not contribs:
            return []

        # 2. Iterate each rule
        for rule in rules:
            window_minutes = rule["window_minutes"]
            min_count = rule["min_event_count"]
            conditions = rule["conditions"]
            
            # Sliding window execution
            for i in range(len(contribs)):
                window_start = datetime.fromisoformat(contribs[i]["created_at"].replace("Z", "+00:00"))
                window_end = window_start + timedelta(minutes=window_minutes)
                
                matched_window_facts = []
                matched_evidence_ids = []
                
                for j in range(i, len(contribs)):
                    current_item = contribs[j]
                    current_time = datetime.fromisoformat(current_item["created_at"].replace("Z", "+00:00"))
                    
                    if current_time > window_end:
                        break
                    
                    # Fetch stored evidence rows for this contribution
                    cursor.execute(
                        "SELECT id, signal_name, value FROM evidence WHERE contribution_id = ?",
                        (current_item["id"],)
                    )
                    evidence_rows = {row["signal_name"]: (row["id"], row["value"]) for row in cursor.fetchall()}
                    
                    # Also include score as a conditional signal
                    evidence_rows["score"] = (-1, current_item.get("score") or 0.0)
                    
                    # Check all conditions in this rule
                    all_passed = True
                    item_evidence_ids = []
                    for cond in conditions:
                        sig_name = cond["signal"]
                        if sig_name not in evidence_rows:
                            all_passed = False
                            break
                        
                        ev_id, ev_val = evidence_rows[sig_name]
                        if not check_operator(ev_val, cond["operator"], cond["threshold"]):
                            all_passed = False
                            break
                        if ev_id != -1:
                            item_evidence_ids.append(ev_id)
                            
                    if all_passed:
                        matched_window_facts.append(current_item["id"])
                        matched_evidence_ids.extend(item_evidence_ids)

                # Check if threshold matches rule's event count
                if len(matched_window_facts) >= min_count:
                    decision_entry = {
                        "username": author,
                        "rule_id": rule["id"],
                        "flag": rule["action"],
                        "evidence_ids": matched_evidence_ids
                    }
                    decisions.append(decision_entry)
                    # Persist decision
                    cursor.execute("""
                        INSERT INTO decisions (username, rule_id, flag, evidence_ids)
                        VALUES (?, ?, ?, ?)
                    """, (
                        author,
                        rule["id"],
                        rule["action"],
                        json.dumps(matched_evidence_ids)
                    ))
                    conn.commit()
                    break # Break window scan for this rule once flagged
    return decisions
