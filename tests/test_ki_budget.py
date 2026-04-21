import json
from pathlib import Path

def test_ki_rules_size_constraint():
    """All KI rules must be < 500 chars. Enforced at test time, not runtime."""
    ki_dir = Path(".nanobot/ki_rules")
    if not ki_dir.exists():
        return
    for ki_file in ki_dir.glob("*.ki.json"):
        data = json.loads(ki_file.read_text(encoding="utf-8"))
        rule_len = len(data.get("rule", ""))
        assert rule_len < 500, (
            f"{ki_file.name}: rule is {rule_len} chars (limit 500). "
            "KI rules must be concise tactical hints, not essays."
        )
