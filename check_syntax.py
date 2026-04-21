import os
import ast

def run():
    count = 0
    errs = 0
    for r, _, f in os.walk('d:/Python/nanobot/nanobot'):
        for file in f:
            if file.endswith('.py'):
                path = os.path.join(r, file)
                count += 1
                try:
                    with open(path, 'r', encoding='utf-8') as p:
                        code = p.read()
                    ast.parse(code)
                except SyntaxError as e:
                    errs += 1
                    print(f"FAILED: {path} - {e}")
    print(f"Checked {count} files, found {errs} errors.")

run()
