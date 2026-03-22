"""Quick verification of shell guard changes and cron cross-day guard."""
import sys
sys.path.insert(0, ".")

# Test 1: Shell guard allows python -c and node -e
from nanobot.agent.tools.shell import ExecTool
t = ExecTool()
r1 = t._guard_command('python -c "print(1)"', '.')
r2 = t._guard_command('node -e "console.log(1)"', '.')
r3 = t._guard_command('rm -rf /', '.')
r4 = t._guard_command('ruby -e "exec(\'bash\')"', '.')

print("=== Shell Guard Tests ===")
print(f"python -c: {'PASS (allowed)' if r1 is None else f'FAIL: {r1}'}")
print(f"node -e:   {'PASS (allowed)' if r2 is None else f'FAIL: {r2}'}")
print(f"rm -rf:    {'PASS (blocked)' if r3 is not None else 'FAIL: not blocked'}")
print(f"ruby -e:   {'PASS (blocked)' if r4 is not None else 'FAIL: not blocked'}")
assert r1 is None, f"python -c should be allowed, got: {r1}"
assert r2 is None, f"node -e should be allowed, got: {r2}"
assert r3 is not None, f"rm -rf should be blocked"
assert r4 is not None, f"ruby -e should be blocked"

# Test 2: Cron cross-day guard
import json
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime, timedelta

from nanobot.cron.service import CronService, _now_ms

# Create a temp store with a job scheduled for yesterday
tmp = Path(tempfile.mkdtemp()) / "jobs.json"
yesterday_8am = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(days=1)
yesterday_ms = int(yesterday_8am.timestamp() * 1000)

# And a job scheduled for today (2 hours ago — should still be caught up)
today_earlier = datetime.now() - timedelta(hours=2)
today_ms = int(today_earlier.timestamp() * 1000)

store_data = {
    "version": 1,
    "jobs": [
        {
            "id": "yesterday",
            "name": "Yesterday Job",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 8 * * *"},
            "payload": {"kind": "agent_turn", "message": "test"},
            "state": {"nextRunAtMs": yesterday_ms},
            "createdAtMs": 0,
            "updatedAtMs": 0,
            "deleteAfterRun": False,
        },
        {
            "id": "today",
            "name": "Today Job", 
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 8 * * *"},
            "payload": {"kind": "agent_turn", "message": "test"},
            "state": {"nextRunAtMs": today_ms},
            "createdAtMs": 0,
            "updatedAtMs": 0,
            "deleteAfterRun": False,
        }
    ]
}
tmp.write_text(json.dumps(store_data))

svc = CronService(tmp)

async def test_cron():
    await svc.start()
    svc.stop()
    
    jobs = svc.list_jobs(include_disabled=True)
    yesterday_job = next(j for j in jobs if j.id == "yesterday")
    today_job = next(j for j in jobs if j.id == "today")
    
    print("\n=== Cron Cross-Day Guard Tests ===")
    print(f"Yesterday job status: {yesterday_job.state.last_status}")
    print(f"Yesterday job skipped: {'PASS' if yesterday_job.state.last_status == 'skipped' else 'FAIL'}")
    assert yesterday_job.state.last_status == "skipped", f"Expected 'skipped', got {yesterday_job.state.last_status}"
    
    # Today's job should NOT be skipped
    print(f"Today job status: {today_job.state.last_status}")
    print(f"Today job NOT skipped: {'PASS' if today_job.state.last_status != 'skipped' else 'FAIL'}")
    assert today_job.state.last_status != "skipped", f"Today's job should not be skipped"
    
    print("\nAll cron tests PASSED!")

asyncio.run(test_cron())

print("\n=== All verification tests passed! ===")
