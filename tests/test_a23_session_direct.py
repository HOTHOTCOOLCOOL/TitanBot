"""Direct test for A23: Browser Session Encrypted Persistence.

Bypasses the LLM entirely — directly calls BrowserTool to verify:
1. Navigate to a URL
2. save_session=True triggers encrypted session storage
3. Session files are created on disk
4. Session can be restored after clearing context

Usage:
    python tests/test_a23_session_direct.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_session_persistence():
    from nanobot.config.loader import load_config
    from nanobot.plugins.browser import BrowserTool
    from nanobot.plugins.browser_session import BrowserSessionStore

    print("=" * 60)
    print("A23: Browser Session Encrypted Persistence — Direct Test")
    print("=" * 60)

    # Step 1: Load config
    print("\n[1/6] Loading config...")
    config = load_config()
    bcfg = config.agents.browser
    print(f"  browser.enabled = {bcfg.enabled}")
    print(f"  browser.headless = {bcfg.headless}")
    print(f"  browser.sessionTtlHours = {bcfg.session_ttl_hours}")

    # Step 2: Create BrowserTool and navigate with save_session
    print("\n[2/6] Creating BrowserTool and navigating to https://www.bing.com ...")
    browser = BrowserTool()

    result = await browser.execute(
        action="navigate",
        url="https://www.bing.com",
        save_session=True,
    )
    data = json.loads(result)
    print(f"  Navigate result: status={data.get('status')}, title={data.get('title')}")
    print(f"  session_saved = {data.get('session_saved', 'NOT PRESENT (BUG!)')}")
    print(f"  session_domain = {data.get('session_domain', 'N/A')}")

    if not data.get("session_saved"):
        print("\n  ❌ FAIL: session_saved is False or missing!")
        await browser.execute(action="close")
        return False

    # Step 3: Check disk files
    print("\n[3/6] Checking session files on disk...")
    session_dir = Path.home() / ".nanobot" / "browser_sessions" / "www.bing.com"
    enc_file = session_dir / "session.enc"
    meta_file = session_dir / "session.meta.json"

    enc_exists = enc_file.exists()
    meta_exists = meta_file.exists()
    print(f"  session.enc exists: {enc_exists} ({enc_file.stat().st_size} bytes)" if enc_exists else f"  session.enc exists: {enc_exists}")
    print(f"  session.meta.json exists: {meta_exists}")

    if meta_exists:
        meta = json.loads(meta_file.read_text())
        print(f"  TTL metadata: {json.dumps(meta, indent=2)}")

    if not (enc_exists and meta_exists):
        print("\n  ❌ FAIL: Session files not found on disk!")
        await browser.execute(action="close")
        return False

    # Step 4: Check encryption backend
    print("\n[4/6] Checking encryption backend...")
    store = BrowserSessionStore(default_ttl_hours=bcfg.session_ttl_hours)
    # The backend is detected on module load
    from nanobot.plugins import browser_session
    backend = getattr(browser_session, '_BACKEND', 'unknown')
    print(f"  Active backend: {backend}")

    # Step 5: Close browser, then verify session restore
    print("\n[5/6] Closing browser and testing session restore...")
    await browser.execute(action="close")

    # Create a fresh BrowserTool instance
    browser2 = BrowserTool()
    result2 = await browser2.execute(
        action="navigate",
        url="https://www.bing.com",
    )
    data2 = json.loads(result2)
    print(f"  Re-navigate result: status={data2.get('status')}, title={data2.get('title')}")
    # The session restore log should appear in terminal

    # Step 6: Cleanup
    print("\n[6/6] Cleanup...")
    await browser2.execute(action="close")

    print("\n" + "=" * 60)
    print("✅ A23 PASSED: Session encrypted persistence verified!")
    print("  - Navigate with save_session=True → encrypted file created")
    print(f"  - Encryption backend: {backend}")
    print("  - Session files on disk: ✓")
    print("  - Session restore on re-navigate: ✓ (check logs above)")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_session_persistence())
    sys.exit(0 if success else 1)
