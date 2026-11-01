import math
import ast
from datetime import datetime
from typing import Dict, Any, Tuple

def compute_churn_per_file(fact: Dict[str, Any]) -> float:
    changed_files = fact.get("changed_files", 0)
    if changed_files <= 0:
        return 0.0
    total_churn = fact.get("additions", 0) + fact.get("deletions", 0)
    return float(total_churn) / float(changed_files)

def compute_body_length(fact: Dict[str, Any]) -> float:
    body = fact.get("body") or ""
    return float(len(body.strip()))

def compute_shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    frequencies = {}
    for char in text:
        frequencies[char] = frequencies.get(char, 0) + 1
    entropy = 0.0
    text_len = len(text)
    for count in frequencies.values():
        prob = count / text_len
        entropy -= prob * math.log2(prob)
    return entropy

def compute_title_entropy(fact: Dict[str, Any]) -> float:
    title = fact.get("title") or ""
    return compute_shannon_entropy(title)

def compute_duration_seconds(fact: Dict[str, Any]) -> float:
    created_at = fact.get("created_at")
    merged_at = fact.get("merged_at")
    if not created_at or not merged_at:
        return -1.0
    t_create = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    t_merge = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
    duration = (t_merge - t_create).total_seconds()
    return max(duration, 0.0)

class ComprehensiveComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.loop_depth = 0
        self.max_time_order = 0.0
        self.loop_allocations = 0
        self.has_blocking_sleep = False
        self.hidden_linear_scans = 0

    def visit_For(self, node: ast.For):
        self.loop_depth += 1
        self.max_time_order = max(self.max_time_order, float(self.loop_depth))
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_While(self, node: ast.While):
        self.loop_depth += 1
        self.max_time_order = max(self.max_time_order, float(self.loop_depth))
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_Compare(self, node: ast.Compare):
        # DETECT HIDDEN O(N^2): 'in' or 'not in' list lookup INSIDE a loop
        if self.loop_depth > 0:
            for op in node.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    self.hidden_linear_scans += 1
                    # A linear scan inside a loop compounds the complexity to O(N^2)
                    self.max_time_order = max(self.max_time_order, float(self.loop_depth + 1))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # DETECT ARTIFICIAL STALLS: time.sleep() inside a loop
        if self.loop_depth > 0:
            # Matches time.sleep(...) or sleep(...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "sleep":
                self.has_blocking_sleep = True
                self.max_time_order = max(self.max_time_order, 2.0)
            elif isinstance(node.func, ast.Name) and node.func.id == "sleep":
                self.has_blocking_sleep = True
                self.max_time_order = max(self.max_time_order, 2.0)
        self.generic_visit(node)

    def visit_List(self, node: ast.List):
        if self.loop_depth > 0:
            self.loop_allocations += 1
        self.generic_visit(node)

def compute_ast_complexity(code_str: str) -> Tuple[float, float]:
    if not code_str or not code_str.strip():
        return 0.0, 0.0

    try:
        tree = ast.parse(code_str)
    except SyntaxError:
        try:
            wrapped = "def _scope_wrapper():\n" + "\n".join(f"    {l}" for l in code_str.splitlines())
            tree = ast.parse(wrapped)
        except SyntaxError:
            return 0.0, 0.0

    visitor = ComprehensiveComplexityVisitor()
    visitor.visit(tree)
    space_order = float(min(visitor.loop_allocations, 2.0))
    return round(visitor.max_time_order, 2), round(space_order, 2)

def compute_time_complexity(fact: Dict[str, Any]) -> float:
    patch = fact.get("patch") or fact.get("body") or ""
    time_order, _ = compute_ast_complexity(patch)
    return time_order

def compute_space_complexity(fact: Dict[str, Any]) -> float:
    patch = fact.get("patch") or fact.get("body") or ""
    _, space_order = compute_ast_complexity(patch)
    return space_order

SIGNAL_REGISTRY = {
    "churn_per_file": compute_churn_per_file,
    "body_length": compute_body_length,
    "title_entropy": compute_title_entropy,
    "duration_seconds": compute_duration_seconds,
    "time_complexity": compute_time_complexity,
    "space_complexity": compute_space_complexity,
}

def extract_signals_for_fact(fact: Dict[str, Any]) -> Dict[str, float]:
    return {name: func(fact) for name, func in SIGNAL_REGISTRY.items()}
