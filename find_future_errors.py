import os
import py_compile

def run():
    count = 0
    errs = 0
    for r, _, f in os.walk('d:/Python/nanobot/nanobot'):
        for file in f:
            if file.endswith('.py'):
                path = os.path.join(r, file)
                count += 1
                try:
                    py_compile.compile(path, doraise=True)
                except py_compile.PyCompileError as e:
                    if 'SyntaxError' in str(e) and ('future' in str(e) or 'annotations' in str(e)):
                        print(f"FAILED: {path}")
                        errs += 1
    print(f"Checked {count} files, found {errs} errors.")

run()
