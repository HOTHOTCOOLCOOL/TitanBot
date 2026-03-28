import ast

def check_file(filepath):
    try:
        source = open(filepath, "r", encoding="utf-8").read()
        tree = ast.parse(source)
    except Exception as e:
        print(f"Failed to parse {filepath}: {e}")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id == 'action' and isinstance(node.ctx, ast.Load):
                print(f"Found 'action' usage at line {node.lineno}")

check_file(r"d:\Python\nanobot\nanobot\agent\loop.py")
