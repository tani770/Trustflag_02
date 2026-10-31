"""Signal extraction for pull-request "facts".

Every signal is a pure function ``fact -> float``.

Missing-value convention: anything that cannot be measured returns ``MISSING``
(NaN), never 0.0 or -1.0, so downstream code can tell "not measurable" apart
from "measured zero". Use ``math.isnan`` / ``pandas.isna`` to check.

The time/space complexity signals are heuristics computed over the *added*
Python lines of a patch (loop nesting, recursion, sorting, container growth).
They are rough estimates, not proofs of big-O.
"""
import ast
import logging
import math
import re
import textwrap
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MISSING = float("nan")
MAX_SPACE_ORDER = 2.0


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _as_float(value: Any, default: float = 0.0) -> float:
    """Coerce to a finite float; None, junk and NaN/inf fall back to default."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string into an aware datetime (naive => UTC)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Simple signals
# --------------------------------------------------------------------------- #
def compute_churn_per_file(fact: Dict[str, Any]) -> float:
    changed_files = _as_float(fact.get("changed_files"))
    if changed_files <= 0:
        return MISSING
    churn = _as_float(fact.get("additions")) + _as_float(fact.get("deletions"))
    return churn / changed_files


def compute_body_length(fact: Dict[str, Any]) -> float:
    # An empty or null PR body is a real observation, so 0.0 is correct here.
    body = fact.get("body") or ""
    return float(len(str(body).strip()))


def compute_shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in Counter(text).values())


def compute_title_entropy(fact: Dict[str, Any]) -> float:
    # Note: entropy is capped at log2(len(title)), so short titles are noisy.
    return compute_shannon_entropy(str(fact.get("title") or ""))


def compute_duration_seconds(fact: Dict[str, Any]) -> float:
    created = _parse_timestamp(fact.get("created_at"))
    merged = _parse_timestamp(fact.get("merged_at"))
    if created is None or merged is None:
        return MISSING
    # merged-before-created is bad data; clamp to 0 rather than go negative.
    return max((merged - created).total_seconds(), 0.0)


# --------------------------------------------------------------------------- #
# Patch handling
# --------------------------------------------------------------------------- #
_HUNK_RE = re.compile(r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")


def _added_python_segments(patch: str) -> List[str]:
    """Return the added lines of each hunk, skipping non-Python files.

    Hunk headers (``@@ -a,b +c,d @@``) are used to count lines, so a removed
    line like ``-- comment`` is never mistaken for a ``---`` file header.
    Input with no diff markers at all is treated as plain source code.
    """
    lines = patch.splitlines()
    if not any(l.startswith(("diff --git", "@@", "+++ ")) for l in lines):
        return [patch]

    segments: List[str] = []
    added: List[str] = []
    is_python = True  # unknown path (e.g. a bare per-file hunk) => try it
    old_left = new_left = 0

    def flush() -> None:
        if added and is_python:
            segments.append("\n".join(added))
        added.clear()

    for line in lines:
        if old_left > 0 or new_left > 0:  # inside a hunk
            tag = line[:1]
            if tag == "+":
                new_left -= 1
                added.append(line[1:])
            elif tag == "-":
                old_left -= 1
            elif tag != "\\":  # "\ No newline at end of file" consumes nothing
                old_left -= 1  # context line
                new_left -= 1
            continue

        hunk = _HUNK_RE.match(line)
        if hunk:
            flush()
            old_left = int(hunk.group(1)) if hunk.group(1) is not None else 1
            new_left = int(hunk.group(2)) if hunk.group(2) is not None else 1
        elif line.startswith("diff --git"):
            flush()
            is_python = line.rstrip().endswith(".py")
        elif line.startswith("+++ "):
            flush()
            path = line[4:].strip()
            if path != "/dev/null":
                is_python = path.endswith(".py")
    flush()
    return segments


_PARSE_ERRORS = (SyntaxError, ValueError, RecursionError, MemoryError)


def _parse_python(code: str) -> Optional[ast.AST]:
    """Parse a code fragment, retrying inside a function body if needed."""
    code = textwrap.dedent(code).strip("\n")
    if not code.strip():
        return None
    wrapped = "def _scope_wrapper():\n" + textwrap.indent(code, "    ")
    for source in (code, wrapped):
        try:
            return ast.parse(source)
        except _PARSE_ERRORS:
            continue
    return None


# --------------------------------------------------------------------------- #
# Complexity heuristics
# --------------------------------------------------------------------------- #
_GROWTH_METHODS = {
    "append", "extend", "add", "update", "insert",
    "appendleft", "extendleft", "setdefault",
}
_CONTAINER_CTORS = {"list", "dict", "set", "deque", "defaultdict", "OrderedDict", "Counter"}


@dataclass
class _Scope:
    name: str
    containers: Dict[str, int] = field(default_factory=dict)  # name -> loop depth at creation
    recursive_sites: int = 0
    recursive_in_loop: bool = False


class ComplexityVisitor(ast.NodeVisitor):
    """Estimates (time_order, space_order) for a parsed fragment.

    Time:  deepest loop/comprehension nesting; sorting adds 1.5 (n log n);
           recursion counts as 1.0, or 2.5 if it branches or recurses in a loop.
    Space: collection-building comprehensions, ``[x] * n``, containers that
           grow in a deeper loop than the one that created them, and
           recursion (call-stack depth).
    """

    def __init__(self) -> None:
        self.depth = 0       # loop/comprehension nesting inside the current function
        self.comp_depth = 0  # nesting of collection-building comprehensions
        self.time_order = 0.0
        self.space_order = 0.0
        self.scopes: List[_Scope] = [_Scope(name="")]

    # -- bookkeeping ------------------------------------------------------- #
    def _bump_time(self, value: float) -> None:
        self.time_order = max(self.time_order, value)

    def _bump_space(self, value: float) -> None:
        self.space_order = max(self.space_order, value)

    @staticmethod
    def _call_target(func: ast.expr) -> Tuple[Optional[str], bool]:
        """Return (name, could_be_a_local_function)."""
        if isinstance(func, ast.Name):
            return func.id, True
        if isinstance(func, ast.Attribute):
            local = isinstance(func.value, ast.Name) and func.value.id in ("self", "cls")
            return func.attr, local
        return None, False

    @staticmethod
    def _is_container_expr(node: ast.expr) -> bool:
        if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
            return True
        if isinstance(node, ast.Call):
            name, _ = ComplexityVisitor._call_target(node.func)
            return name in _CONTAINER_CTORS
        return False

    def _note_growth(self, target: ast.expr) -> None:
        """Record growth of a known container inside a deeper loop than its creation."""
        while isinstance(target, ast.Subscript):
            target = target.value
        if isinstance(target, ast.Name):
            created_at = self.scopes[-1].containers.get(target.id)
            if created_at is not None and self.depth > created_at:
                self._bump_space(float(self.depth - created_at))

    # -- scopes ------------------------------------------------------------ #
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        scope = _Scope(name=node.name)
        saved = (self.depth, self.comp_depth)
        self.scopes.append(scope)
        self.depth = self.comp_depth = 0
        self.generic_visit(node)
        self.scopes.pop()
        self.depth, self.comp_depth = saved
        if scope.recursive_sites:
            branching = scope.recursive_sites > 1 or scope.recursive_in_loop
            self._bump_time(2.5 if branching else 1.0)
            self._bump_space(1.0)  # call-stack depth

    visit_AsyncFunctionDef = visit_FunctionDef

    # -- loops ------------------------------------------------------------- #
    def _run_loop(self, body: List[ast.AST], orelse: List[ast.AST]) -> None:
        self.depth += 1
        self._bump_time(float(self.depth))
        for child in body:
            self.visit(child)
        self.depth -= 1
        for child in orelse:
            self.visit(child)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)  # evaluated once, outside the loop
        self._run_loop(node.body, node.orelse)

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While) -> None:
        self._run_loop([node.test, *node.body], node.orelse)  # test runs every iteration

    def _visit_comprehension(self, node: Any, elements: List[ast.expr], collects: bool) -> None:
        gens = node.generators
        self.visit(gens[0].iter)  # the first iterable is evaluated once, outside
        self.depth += len(gens)
        self._bump_time(float(self.depth))
        if collects:
            self.comp_depth += 1
            self._bump_space(float(self.comp_depth))
        for i, gen in enumerate(gens):
            if i:
                self.visit(gen.iter)
            for cond in gen.ifs:
                self.visit(cond)
        for element in elements:
            self.visit(element)
        self.depth -= len(gens)
        if collects:
            self.comp_depth -= 1

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, [node.elt], collects=True)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, [node.elt], collects=True)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, [node.key, node.value], collects=True)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, [node.elt], collects=False)

    # -- calls / allocation ------------------------------------------------ #
    def visit_Call(self, node: ast.Call) -> None:
        name, local = self._call_target(node.func)
        if name:
            if local:
                for scope in reversed(self.scopes):
                    if scope.name == name:
                        scope.recursive_sites += 1
                        scope.recursive_in_loop |= self.depth > 0
                        break
            if name in ("sorted", "sort"):
                self._bump_time(self.depth + 1.5)
            if name in _GROWTH_METHODS and isinstance(node.func, ast.Attribute):
                self._note_growth(node.func.value)
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, ast.Mult):
            left, right = node.left, node.right
            if (isinstance(left, ast.List) and not isinstance(right, ast.Constant)) or (
                isinstance(right, ast.List) and not isinstance(left, ast.Constant)
            ):
                self._bump_space(1.0 + self.comp_depth)  # [x] * n
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._is_container_expr(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.scopes[-1].containers[target.id] = self.depth
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                self._note_growth(target)  # x[key] = value
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if (
            node.value is not None
            and isinstance(node.target, ast.Name)
            and self._is_container_expr(node.value)
        ):
            self.scopes[-1].containers[node.target.id] = self.depth
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.op, (ast.Add, ast.BitOr)):  # x += [...], x |= {...}
            self._note_growth(node.target)
        self.generic_visit(node)


def _analyze_source(code: str) -> Optional[Tuple[float, float]]:
    tree = _parse_python(code)
    if tree is None:
        return None
    visitor = ComplexityVisitor()
    try:
        visitor.visit(tree)
    except RecursionError:
        return None
    return round(visitor.time_order, 2), round(min(visitor.space_order, MAX_SPACE_ORDER), 2)


@lru_cache(maxsize=1024)
def compute_ast_complexity(code_str: str) -> Tuple[float, float]:
    """Return (time_order, space_order) for Python source or a unified diff.

    Returns (MISSING, MISSING) when there is nothing analyzable: no Python
    changes, or code that does not parse. Results are cached per input string,
    so time and space signals share a single parse.
    """
    if not code_str or not code_str.strip():
        return MISSING, MISSING
    results = [
        r for r in (_analyze_source(seg) for seg in _added_python_segments(code_str)) if r is not None
    ]
    if not results:
        return MISSING, MISSING
    return max(t for t, _ in results), max(s for _, s in results)


def compute_code_complexity(fact: Dict[str, Any]) -> Tuple[float, float]:
    # Only the patch is code. PR bodies are prose and are deliberately not parsed.
    patch = fact.get("patch")
    if not isinstance(patch, str):
        return MISSING, MISSING
    return compute_ast_complexity(patch)


def compute_time_complexity(fact: Dict[str, Any]) -> float:
    return compute_code_complexity(fact)[0]


def compute_space_complexity(fact: Dict[str, Any]) -> float:
    return compute_code_complexity(fact)[1]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
SIGNAL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], float]] = {
    "churn_per_file": compute_churn_per_file,
    "body_length": compute_body_length,
    "title_entropy": compute_title_entropy,
    "duration_seconds": compute_duration_seconds,
    "time_complexity": compute_time_complexity,
    "space_complexity": compute_space_complexity,
}


def extract_signals_for_fact(fact: Dict[str, Any]) -> Dict[str, float]:
    """Compute every registered signal; one failing signal never sinks the rest."""
    signals: Dict[str, float] = {}
    for name, func in SIGNAL_REGISTRY.items():
        try:
            signals[name] = func(fact)
        except Exception:  # noqa: BLE001 - isolate bad facts, but keep the traceback
            logger.warning("signal %r failed", name, exc_info=True)
            signals[name] = MISSING
    return signals