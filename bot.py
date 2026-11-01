import httpx
from typing import Dict, Any, List

GITHUB_API_BASE = "https://api.github.com"

def get_auth_headers(token: str) -> Dict[str, str]:
    clean_token = token.strip()
    auth_prefix = "token" if clean_token.startswith("ghp_") else "Bearer"
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"{auth_prefix} {clean_token}",
        "User-Agent": "TrustFlag-Bot/3.0"
    }

async def post_pr_audit_comment(
    repo: str,
    pr_number: int,
    author: str,
    score: float,
    decisions: List[Dict[str, Any]],
    signals: Dict[str, float],
    appeal_url: str,
    token: str,
    client: httpx.AsyncClient
) -> None:
    if not token:
        return

    accuracy_pct = signals.get("accuracy", 0.0) * 100.0
    is_100_percent = accuracy_pct >= 100.0 and len(decisions) == 0

    badge = "✅ **AUDIT PASSED (100% ACCURATE)**" if is_100_percent else "❌ **AUDIT FAILED (ACCURACY DEFICIT DETECTED)**"

    comment_body = f"""### {badge}
**Contributor:** @{author} | **Functional Accuracy:** `{accuracy_pct:.1f}%`

#### Accuracy Verification
| Verification Check | Result | Requirement |
| :--- | :--- | :--- |
| **Code Accuracy Score** | `{accuracy_pct:.1f}%` | **Must be 100.0%** |
| **Syntax & Compilation** | {'✅ PASS' if signals.get('syntax_valid', 0.0) == 1.0 else '❌ FAIL'} | Zero syntax errors |
| **Test Assertions** | {int(signals.get('tests_passed', 0))}/{int(signals.get('tests_total', 0))} Passed | 100% Pass Rate |
"""

    if not is_100_percent:
        comment_body += "\n#### ⚠️ Rejection Reason:\n"
        for d in decisions:
            comment_body += f"- **Rule:** `{d['rule_id']}` | **Action:** `{d['flag']}`\n"
        comment_body += f"\n> **Resolution:** Fix the failing test cases or inaccurate calculations to reach 100% accuracy before merging.\n"

    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    await client.post(url, headers=get_auth_headers(token), json={"body": comment_body})
