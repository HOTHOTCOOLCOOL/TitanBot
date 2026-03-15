import asyncio
import time
from nanobot.agent.tools.attachment_analyzer import AttachmentAnalyzerTool
from nanobot.compute import shutdown_broker
from pathlib import Path
import os
import tempfile

async def heartbeat():
    """Simulate a heartbeat that shouldn't be blocked"""
    for i in range(10):
        print(f"[{time.time():.2f}] Heartbeat {i+1}")
        await asyncio.sleep(0.5)

async def run_cpu_heavy_task(test_file: str):
    """Simulate a CPU-bound attachment parsing request"""
    print(f"[{time.time():.2f}] Starting CPU parsing of {test_file}")
    
    analyzer = AttachmentAnalyzerTool()
    # Create the tool locally
    
    # Let's run the parsing task
    # To really simulate CPU-bound, let's create a huge text file if we don't have a large PDF/Excel handy
    start = time.time()
    result = await analyzer.execute(action="parse", file_path=test_file)
    end = time.time()
    
    print(f"[{time.time():.2f}] Parsing finished in {end - start:.2f} seconds.")
    print(f"[{time.time():.2f}] Output length: {len(result)}")
    return result

async def main():
    # 1. Create a dummy test file
    import pandas as pd
    import numpy as np
    
    test_file = "large_test.csv"
    print(f"Generating dummy large CSV ({test_file})...")
    # Generate 1M rows to make pandas spin
    df = pd.DataFrame(np.random.randint(0,100,size=(1000000, 4)), columns=list('ABCD'))
    df.to_csv(test_file, index=False)
    
    # 2. Run simulation
    print("Starting simulation...")
    
    try:
        # Run heartbeat and heavy task concurrently
        await asyncio.gather(
            heartbeat(),
            run_cpu_heavy_task(test_file)
        )
    finally:
        shutdown_broker(wait=False)
        if os.path.exists(test_file):
            os.remove(test_file)
            
if __name__ == "__main__":
    asyncio.run(main())
