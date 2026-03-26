import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to sys.path if needed
sys.path.append(str(Path(__file__).parent))

from nanobot.plugins.browser import BrowserTool
from nanobot.plugins.browser_session import get_encryption_backend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestSessionPersist")

async def main():
    logger.info(f"Using encryption backend: {get_encryption_backend()}")
    
    logger.info("--- Step 1: Navigating and Saving Session ---")
    tool1 = BrowserTool()
    
    # Mock config and dependencies
    tool1._config_loaded = True
    
    from nanobot.plugins.trust_manager import TrustManager
    from nanobot.plugins.browser_session import BrowserSessionStore
    
    session_dir = Path(__file__).parent / ".test_sessions"
    tool1._trust_manager = TrustManager(config_trusted=["httpbin.org"])
    tool1._session_store = BrowserSessionStore(base_dir=session_dir)
    
    # We still need to call setup for Playwright initialization
    await tool1.setup()
    
    # Action 1: Set cookie and save session
    logger.info("Setting cookie at httpbin.org...")
    res1 = await tool1.execute(
        action="login", 
        url="https://httpbin.org/cookies/set/my_test_cookie/super_secret_value",
        save_session=True
    )
    logger.info(f"Result 1: {res1}")
    
    # Teardown tool1
    await tool1.teardown()
    
    logger.info("--- Step 2: Inspecting File System ---")
    # Verify the file is encrypted on disk
    session_file = Path(tool1._session_store._base_dir) / "httpbin.org" / "session.enc"
    if session_file.exists():
        content = session_file.read_bytes()
        logger.info(f"Session file exists, size: {len(content)} bytes")
        if b"super_secret_value" in content:
            logger.error("DANGER: 'super_secret_value' found in plaintext in session.enc!")
            sys.exit(1)
        else:
            logger.info("SUCCESS: 'super_secret_value' is NOT in plaintext.")
    else:
        logger.error("Session file was not created!")
        sys.exit(1)
        
    logger.info("--- Step 3: Restoring Session ---")
    tool2 = BrowserTool()
    tool2._config_loaded = True
    tool2._trust_manager = TrustManager(config_trusted=["httpbin.org"])
    tool2._session_store = BrowserSessionStore(base_dir=session_dir)
    await tool2.setup()
    
    # Action 2: Navigate and then read cookies
    logger.info("Navigating to httpbin.org/cookies...")
    await tool2.execute(
        action="navigate",
        url="https://httpbin.org/cookies"
    )
    
    logger.info("Extracting content...")
    res2 = await tool2.execute(
        action="content"
    )
    logger.info(f"Result 2: {res2}")
    
    if "super_secret_value" in res2:
        logger.info("SUCCESS: The session and cookie were successfully restored!")
    else:
        logger.error("FAILURE: The cookie was not restored.")
        
    await tool2.teardown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as e:
        if "I/O operation on closed pipe" in str(e):
            pass
        else:
            raise
