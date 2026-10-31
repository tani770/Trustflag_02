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

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.current_loop_depth = 0
        self.max_loop_depth = 0
        self.loop_allocations = 0
        self.current_function = ""
        self.recursive_calls = 0

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        old = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old

    def visit_For(self, node: ast.For):
        self.current_loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.current_loop_depth)
        self.generic_visit(node)
        self.current_loop_depth -= 1

    def visit_While(self, node: ast.While):
        self.current_loop_depth += 1
        self.max_loop_depth = max(self.max_loop_depth, self.current_loop_depth)
        self.generic_visit(node)
        self.current_loop_depth -= 1

    def visit_ListComp(self, node: ast.ListComp):
        self.current_loop_depth += len(node.generators)
        self.max_loop_depth = max(self.max_loop_depth, self.current_loop_depth)
        if self.current_loop_depth > 0:
            self.loop_allocations += 1
        self.generic_visit(node)
        self.current_loop_depth -= len(node.generators)

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == self.current_function:
            self.recursive_calls += 1
        self.generic_visit(node)

    def visit_List(self, node: ast.List):
        if self.current_loop_depth > 0:
            self.loop_allocations += 1
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict):
        if self.current_loop_depth > 0:
            self.loop_allocations += 1
        self.generic_visit(node)

def compute_code_complexity(fact: Dict[str, Any]) -> Tuple[float, float]:
    patch = fact.get("patch") or fact.get("body") or ""
    if not patch.strip():
        return 0.0, 0.0

    # 1. Cleanly strip git diff metadata (@@, +++, ---, diff)
    code_lines = []
    has_diff_headers = any(line.strip().startswith(("@@", "diff --git", "--- ", "+++ ")) for line in patch.splitlines())

    for raw_line in patch.splitlines():
        line = raw_line.strip()
        if line.startswith(("@@", "diff --git", "---", "+++", "index ")):
            continue
        if has_diff_headers:
            if raw_line.startswith("+"):
                code_lines.append(raw_line[1:])  # Strip the '+' prefix
        else:
            code_lines.append(raw_line)

    code_str = "\n".join(code_lines).strip()
    if not code_str:
        return 0.0, 0.0

    # 2. Parse AST (with indentation fallback wrapper)
    try:
        tree = ast.parse(code_str)
    except SyntaxError:
        try:
            wrapped = "def _scope_wrapper():\n" + "\n".join(f"    {l}" for l in code_str.splitlines())
            tree = ast.parse(wrapped)
        except SyntaxError:
            return 0.0, 0.0

    v = ComplexityVisitor()
    v.visit(tree)
    time_order = float(v.max_loop_depth)
    if v.recursive_calls > 0:
        time_order = max(time_order, 2.5)
    space_order = float(min(v.loop_allocations, 2.0))
    return round(time_order, 2), round(space_order, 2)

def compute_time_complexity(fact: Dict[str, Any]) -> float:
    time_order, _ = compute_code_complexity(fact)
    return time_order

def compute_space_complexity(fact: Dict[str, Any]) -> float:
    _, space_order = compute_code_complexity(fact)
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
