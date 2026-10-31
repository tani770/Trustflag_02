CREATE TABLE IF NOT EXISTS contributions (
    id TEXT PRIMARY KEY,
    author TEXT NOT NULL,
    repo TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    additions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    changed_files INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL,
    merged_at TIMESTAMP,
    is_fork_target BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contribution_id TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    value REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(contribution_id) REFERENCES contributions(id)
);

CREATE TABLE IF NOT EXISTS scores (
    contribution_id TEXT PRIMARY KEY,
    score REAL NOT NULL,
    FOREIGN KEY(contribution_id) REFERENCES contributions(id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    flag TEXT NOT NULL,
    evidence_ids TEXT NOT NULL, -- JSON array of evidence IDs
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(decision_id) REFERENCES decisions(id)
);
