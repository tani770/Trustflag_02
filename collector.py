import sqlite3
from typing import Dict, Any, List
import httpx

GITHUB_API_BASE = "https://api.github.com"

def init_db(db_path: str = "audit.db") -> None:
    with open("schema.sql", "r") as f:
        schema = f.read()
    with sqlite3.connect(db_path) as conn:
        conn.executescript(schema)

def parse_pr_fact(pr_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"{pr_data['base']['repo']['full_name']}#{pr_data['number']}",
        "author": pr_data["user"]["login"],
        "repo": pr_data["base"]["repo"]["full_name"],
        "pr_number": pr_data["number"],
        "title": pr_data.get("title") or "",
        "body": pr_data.get("body") or "",
        "additions": pr_data.get("additions", 0),
        "deletions": pr_data.get("deletions", 0),
        "changed_files": pr_data.get("changed_files", 0),
        "created_at": pr_data["created_at"],
        "merged_at": pr_data.get("merged_at"),
        "is_fork_target": bool(pr_data["base"]["repo"].get("fork", False))
    }

async def fetch_user_contributions(repo: str, token: str, client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}"
    }
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls?state=all&per_page=100"
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    pulls = response.json()
    
    detailed_facts = []
    for pr in pulls:
        detail_resp = await client.get(pr["url"], headers=headers)
        if detail_resp.status_code == 200:
            detailed_facts.append(parse_pr_fact(detail_resp.json()))
    return detailed_facts

def save_contributions(facts: List[Dict[str, Any]], db_path: str = "audit.db") -> None:
    query = """
    INSERT INTO contributions (
        id, author, repo, pr_number, title, body, additions, deletions, 
        changed_files, created_at, merged_at, is_fork_target
    ) VALUES (
        :id, :author, :repo, :pr_number, :title, :body, :additions, :deletions,
        :changed_files, :created_at, :merged_at, :is_fork_target
    ) ON CONFLICT(id) DO UPDATE SET
        body=excluded.body,
        additions=excluded.additions,
        deletions=excluded.deletions,
        changed_files=excluded.changed_files,
        merged_at=excluded.merged_at;
    """
    with sqlite3.connect(db_path) as conn:
        conn.executemany(query, facts)
