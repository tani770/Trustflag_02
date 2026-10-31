import ast

# 1. AST Complexity Analyzer
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

def analyze_code(code: str):
    tree = ast.parse(code)
    visitor = ComplexityVisitor()
    visitor.visit(tree)
    time_order = float(visitor.max_loop_depth)
    if visitor.recursive_calls > 0:
        time_order = max(time_order, 2.5)
    space_order = float(min(visitor.loop_allocations, 2.0))
    return time_order, space_order

# 2. Execute and print immediately
print("\n" + "="*50)
print("RUNNING STATIC COMPLEXITY ANALYZER")
print("="*50)

# Case A: Linear O(N)
c1 = """
def linear_search(arr, target):
    for x in arr:
        if x == target: return True
    return False
"""
t1, s1 = analyze_code(c1)
print(f"[✓] Case 1 (Linear):     Time = O(N^{int(t1)}) | Space Allocations = {int(s1)}")

# Case B: Quadratic O(N^2)
c2 = """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                temp = [arr[j]] # in-loop allocation
"""
t2, s2 = analyze_code(c2)
print(f"[✓] Case 2 (Quadratic):  Time = O(N^{int(t2)}) | Space Allocations = {int(s2)}")

# Case C: Cubic O(N^3)
c3 = """
def matrix_mult(A, B, C):
    for i in range(len(A)):
        for j in range(len(B)):
            for k in range(len(C)):
                val = A[i][k] * B[k][j]
"""
t3, s3 = analyze_code(c3)
print(f"[✓] Case 3 (Cubic):      Time = O(N^{int(t3)}) | Space Allocations = {int(s3)}")
print("="*50 + "\n")