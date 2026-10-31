import sqlite3
import json
import hmac
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request, Header, status
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from signals import extract_signals_for_fact
from scoring import calculate_quality_score
from rules import run_window_audit

app = FastAPI(title="Sybil Quality & Audit Engine", version="2.0.0")

# Robust absolute paths relative to api.py
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
DB_PATH = str(BASE_DIR / "audit.db")

WEBHOOK_SECRET = "your_shared_webhook_secret_here"


class AppealRequest(BaseModel):
    decision_id: int
    reason: str = Field(..., min_length=10, max_length=1000)


class ResolveAppealRequest(BaseModel):
    resolution: str = Field(..., pattern="^(APPROVED|REJECTED)$")


@app.get("/profile/{username}", response_model=None)
def get_user_profile(username: str, request: Request):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. Fetch active decisions
        cursor.execute("SELECT * FROM decisions WHERE username = ?", (username,))
        decisions = [dict(row) for row in cursor.fetchall()]
        for d in decisions:
            try:
                d["evidence_ids"] = json.loads(d["evidence_ids"])
            except Exception:
                d["evidence_ids"] = []

        # 2. Fetch raw contributions
        cursor.execute("SELECT * FROM contributions WHERE author = ? ORDER BY created_at DESC", (username,))
        contributions = [dict(row) for row in cursor.fetchall()]

        # 3. Fetch scores
        contrib_ids = [c["id"] for c in contributions]
        scores = {}
        if contrib_ids:
            placeholders = ",".join("?" for _ in contrib_ids)
            cursor.execute(f"SELECT * FROM scores WHERE contribution_id IN ({placeholders})", contrib_ids)
            scores = {row["contribution_id"]: row["score"] for row in cursor.fetchall()}

        for c in contributions:
            c["score"] = scores.get(c["id"], None)

        status_verdict = "FLAGGED" if len(decisions) > 0 else "CLEAN"

        context_data = {
            "request": request,
            "username": username,
            "status": status_verdict,
            "decision_count": len(decisions),
            "decisions": decisions,
            "contributions": contributions
        }

        # Content negotiation: serve HTML to browsers, JSON to API clients
        if "text/html" in request.headers.get("accept", ""):
            return templates.TemplateResponse(
                request=request,
                name="profile.html",
                context=context_data
            )

        return {
            "username": username,
            "status": status_verdict,
            "decision_count": len(decisions),
            "decisions": decisions,
            "contributions": contributions
        }


@app.post("/appeal", status_code=status.HTTP_201_CREATED)
def submit_appeal(appeal: AppealRequest) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT id, flag FROM decisions WHERE id = ?", (appeal.decision_id,))
        decision = cursor.fetchone()
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Decision ID does not exist."
            )

        cursor.execute("""
            INSERT INTO appeals (decision_id, reason, status)
            VALUES (?, ?, 'PENDING')
        """, (appeal.decision_id, appeal.reason))
        conn.commit()

        return {
            "appeal_id": cursor.lastrowid,
            "decision_id": appeal.decision_id,
            "status": "PENDING",
            "message": "Appeal logged successfully."
        }


@app.get("/admin/appeals", response_class=HTMLResponse)
def view_admin_appeals(request: Request):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT a.id, a.decision_id, a.reason, a.status, a.created_at,
                   d.username, d.rule_id, d.evidence_ids
            FROM appeals a
            LEFT JOIN decisions d ON a.decision_id = d.id
            ORDER BY a.created_at DESC
        """)
        appeals = [dict(row) for row in cursor.fetchall()]

        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"request": request, "appeals": appeals}
        )


@app.post("/admin/appeals/{appeal_id}/resolve")
def resolve_appeal(appeal_id: int, body: ResolveAppealRequest) -> Dict[str, Any]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,))
        appeal = cursor.fetchone()
        if not appeal:
            raise HTTPException(status_code=404, detail="Appeal not found.")

        cursor.execute("UPDATE appeals SET status = ? WHERE id = ?", (body.resolution, appeal_id))

        if body.resolution == "APPROVED":
            cursor.execute("DELETE FROM decisions WHERE id = ?", (appeal["decision_id"],))

        conn.commit()

        return {
            "appeal_id": appeal_id,
            "status": body.resolution,
            "cleared_decision_id": appeal["decision_id"] if body.resolution == "APPROVED" else None
        }


@app.get("/badge/{username}")
def get_user_badge(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as flag_count FROM decisions WHERE username = ?", (username,))
        flag_count = cursor.fetchone()["flag_count"]

        cursor.execute("""
            SELECT AVG(s.score) as avg_score
            FROM scores s
            JOIN contributions c ON s.contribution_id = c.id
            WHERE c.author = ?
        """, (username,))
        row = cursor.fetchone()
        avg_score = round(row["avg_score"], 2) if (row and row["avg_score"] is not None) else "N/A"

    if flag_count > 0:
        color = "#e11d48"
        status_text = f"FLAGGED ({flag_count})"
    else:
        color = "#10b981"
        status_text = f"CLEAN | SCORE {avg_score}"

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="210" height="28">
        <linearGradient id="b" x2="0" y2="100%">
            <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
            <stop offset="1" stop-opacity=".1"/>
        </linearGradient>
        <clipPath id="a">
            <rect width="210" height="28" rx="4"/>
        </clipPath>
        <g clip-path="url(#a)">
            <path fill="#1e293b" d="M0 0h90v28H0z"/>
            <path fill="{color}" d="M90 0h120v28H90z"/>
            <path fill="url(#b)" d="M0 0h210v28H0z"/>
        </g>
        <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
            <text x="45" y="18" fill="#94a3b8">TrustFlag</text>
            <text x="150" y="18" font-weight="bold">{status_text}</text>
        </g>
    </svg>"""

    return Response(content=svg_content, media_type="image/svg+xml")


@app.post("/webhook/github", status_code=status.HTTP_200_OK)
async def github_webhook_receiver(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None)
):
    raw_payload = await request.body()

    if WEBHOOK_SECRET and WEBHOOK_SECRET != "your_shared_webhook_secret_here":
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing webhook signature.")
        expected_sig = "sha256=" + hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            raw_payload,
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_sig, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid webhook signature.")

    payload = await request.json()
    action = payload.get("action")

    if "pull_request" not in payload or action not in ["opened", "synchronize", "closed"]:
        return {"status": "ignored", "reason": f"Action '{action}' is not audited."}

    pr_data = payload["pull_request"]
    repo_name = payload["repository"]["full_name"]
    author = pr_data["user"]["login"]

    fact = {
        "id": f"{repo_name}#{pr_data['number']}",
        "author": author,
        "repo": repo_name,
        "pr_number": pr_data["number"],
        "title": pr_data.get("title") or "",
        "body": pr_data.get("body") or "",
        "additions": pr_data.get("additions", 0),
        "deletions": pr_data.get("deletions", 0),
        "changed_files": pr_data.get("changed_files", 0),
        "created_at": pr_data["created_at"],
        "merged_at": pr_data.get("merged_at"),
        "is_fork_target": bool(payload["repository"].get("fork", False))
    }

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO contributions (
                id, author, repo, pr_number, title, body, additions, deletions, 
                changed_files, created_at, merged_at, is_fork_target
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                body=excluded.body,
                additions=excluded.additions,
                deletions=excluded.deletions,
                changed_files=excluded.changed_files,
                merged_at=excluded.merged_at;
        """, (
            fact["id"], fact["author"], fact["repo"], fact["pr_number"],
            fact["title"], fact["body"], fact["additions"], fact["deletions"],
            fact["changed_files"], fact["created_at"], fact["merged_at"], fact["is_fork_target"]
        ))

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

    decisions = run_window_audit(author, DB_PATH)

    return {
        "status": "processed",
        "contribution_id": fact["id"],
        "quality_score": score,
        "flags_raised": len(decisions)
    }