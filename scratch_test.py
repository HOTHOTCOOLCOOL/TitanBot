import re
from pathlib import Path
cwd = "d:/Python/nanobot"
cmd = "dir \"d:\\Python\" /b"

cwd_path = Path(cwd).resolve()
win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
print("win_paths:", win_paths)
posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)
print("posix_paths:", posix_paths)

for raw in win_paths + posix_paths:
    print("Evaluating:", raw)
    p = Path(raw.strip()).resolve()
    print("p is_absolute:", p.is_absolute())
    print("cwd_path in p.parents:", cwd_path in p.parents)
    print("p != cwd_path:", p != cwd_path)
    if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
        print("BLOCKED!")
    else:
        print("ALLOWED!")
