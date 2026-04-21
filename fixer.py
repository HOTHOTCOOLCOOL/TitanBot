import re
import ast
import os
from pathlib import Path

def get_violations():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from tests.test_phase55_automated import Phase55ArchitectureVisitor, NANOBOT_DIR
    violations = {}
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
                violations[filepath] = visitor.bad_async_execpts
    return violations

def fix_excepts(filepath, lines_to_fix):
    lines = filepath.read_text(encoding="utf-8").splitlines()
    
    # Check if we need to import asyncio
    has_asyncio = any("import asyncio" in line for line in lines)
    
    # Process from bottom up to not mess up line numbers
    for lineno in sorted(lines_to_fix, reverse=True):
        idx = lineno - 1
        line = lines[idx]
        
        # Match 'except Exception as e:' or 'except Exception:'
        match = re.match(r"^(\s*)except\s+Exception(?:\s+as\s+(\w+))?:(.*)$", line)
        if match:
            indent = match.group(1)
            var_name = match.group(2)
            rest = match.group(3)
            
            if not var_name:
                var_name = "_e"
                lines[idx] = f"{indent}except Exception as {var_name}:{rest}"
                
            injection = [
                f"{indent}    if isinstance({var_name}, asyncio.CancelledError):",
                f"{indent}        raise"
            ]
            lines.insert(idx + 1, injection[1])
            lines.insert(idx + 1, injection[0])
            
        else:
            print(f"Could not parse line {lineno} in {filepath}: {line}")
            
    if not has_asyncio:
        lines.insert(0, "import asyncio")
        
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

def main():
    violations = get_violations()
    print(f"Found violations in {len(violations)} files.")
    for filepath, lines_to_fix in violations.items():
        print(f"Fixing {filepath} ({len(lines_to_fix)} violations)")
        fix_excepts(filepath, list(set(lines_to_fix)))

if __name__ == "__main__":
    main()
