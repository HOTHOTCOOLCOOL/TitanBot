import ast
import os
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
NANOBOT_DIR = PROJECT_ROOT / "nanobot"

# Files/dirs exempt from the "No Print" rule (Tool Payload System)
NO_PRINT_EXEMPTIONS = [
    NANOBOT_DIR / 'agent' / 'sandbox_worker.py',
    NANOBOT_DIR / 'onboard.py',
    NANOBOT_DIR / "skills",
    NANOBOT_DIR / "scripts",
]

def is_exempt_from_print_rule(filepath: Path) -> bool:
    for exemption in NO_PRINT_EXEMPTIONS:
        if filepath.is_relative_to(exemption):
            return True
    return False

class Phase55ArchitectureVisitor(ast.NodeVisitor):
    def __init__(self):
        self.print_calls = []
        self.bad_async_execpts = []
        
    def visit_Call(self, node):
        # Look for print() calls
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            self.print_calls.append(node.lineno)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        # In async functions, check for try-except blocks
        for child in ast.walk(node):
            if isinstance(child, ast.Try):
                for handler in child.handlers:
                    # Check if it catches Exception or a bare except
                    is_blanket_except = False
                    if handler.type is None:
                        is_blanket_except = True
                    elif isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                        is_blanket_except = True
                    elif isinstance(handler.type, ast.Tuple):
                        for el in handler.type.elts:
                            if isinstance(el, ast.Name) and el.id == "Exception":
                                is_blanket_except = True
                                break
                    
                    if is_blanket_except:
                        # Scan the body of the except block for an asyncio.CancelledError check
                        has_guard = False
                        body_code = " ".join([ast.unparse(stmt) for stmt in handler.body])
                        if "asyncio.CancelledError" in body_code and "raise" in body_code:
                            has_guard = True
                        
                        if not has_guard:
                            self.bad_async_execpts.append(handler.lineno)
                            
        self.generic_visit(node)

def test_phase55_no_print_in_host_agent():
    violations = []
    
    for root, _, files in os.walk(NANOBOT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            
            filepath = Path(root) / file
            if is_exempt_from_print_rule(filepath):
                continue
                
            code = filepath.read_text(encoding="utf-8")
            try:
                tree = ast.parse(code, filename=str(filepath))
            except SyntaxError:
                continue
                
            visitor = Phase55ArchitectureVisitor()
            visitor.visit(tree)
            
            if visitor.print_calls:
                for line in visitor.print_calls:
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line}")
                    
    assert not violations, f"Found {len(violations)} illegal print() calls in Host Agent:\\n" + "\\n".join(violations)

def test_phase55_async_cancelled_error_guard():
    violations = []
    
    for root, _, files in os.walk(NANOBOT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            
            filepath = Path(root) / file
            code = filepath.read_text(encoding="utf-8")
            try:
                tree = ast.parse(code, filename=str(filepath))
            except SyntaxError:
                continue
                
            visitor = Phase55ArchitectureVisitor()
            visitor.visit(tree)
            
            if visitor.bad_async_execpts:
                for line in visitor.bad_async_execpts:
                    violations.append(f"{filepath.relative_to(PROJECT_ROOT)}:{line}")
                    
    assert not violations, f"Found {len(violations)} async except Exception blocks missing asyncio.CancelledError guards:\\n" + "\\n".join(violations)
