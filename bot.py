import httpx
from typing import Dict, Any, List

GITHUB_API_BASE = "https://api.github.com"

def get_auth_headers(token: str) -> Dict[str, str]:
    clean_token = token.strip()
    auth_prefix = "token" if clean_token.startswith("ghp_") else "Bearer"
    return {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"{auth_prefix} {clean_token}",
        "User-Agent": "TrustFlag-Bot/2.0"
    }

async def post_github_status(repo: str, sha: str, state: str, description: str, target_url: str, token: str, client: httpx.AsyncClient) -> None:
    if not token or not sha:
        return
    url = f"{GITHUB_API_BASE}/repos/{repo}/statuses/{sha}"
    payload = {
        "state": state,
        "target_url": target_url,
        "description": description[:140],
        "context": "TrustFlag / Code Quality & Efficiency"
    }
    await client.post(url, headers=get_auth_headers(token), json=payload)

async def post_pr_audit_comment(repo: str, pr_number: int, author: str, score: float, decisions: List[Dict[str, Any]], signals: Dict[str, float], appeal_url: str, token: str, client: httpx.AsyncClient) -> None:
    if not token:
        return
    is_flagged = len(decisions) > 0
    badge = "❌ **AUDIT FAILED (CHANGES REQUESTED)**" if is_flagged else "✅ **AUDIT PASSED**"
    comment_body = f"""### {badge}
**Contributor:** @{author} | **Quality Score:** `{score}` / 1.00

#### Signal Analysis
| Signal Metric | Value | Reference Threshold |
| :--- | :--- | :--- |
| **Time Complexity** | `O(N^{int(signals.get('time_complexity', 0))})` | `< O(N^2)` |
| **Space Complexity** | `O(N^{int(signals.get('space_complexity', 0))})` | In-loop allocations |
| **Diff Churn per File** | `{signals.get('churn_per_file', 0)} lines` | Quality baseline |
| **Commit/Title Entropy** | `{signals.get('title_entropy', 0):.2f} bits` | `> 2.50` (Anti-bot) |
"""
    if is_flagged:
        comment_body += "\n#### ⚠️ Rule Violations Triggered:\n"
        for d in decisions:
            comment_body += f"- **Rule:** `{d['rule_id']}` | **Action:** `{d['flag']}`\n"
        comment_body += f"\n> **Dispute this decision:** You can submit an explanation via the [Auditor Appeal Desk]({appeal_url}).\n"

    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    await client.post(url, headers=get_auth_headers(token), json={"body": comment_body})
