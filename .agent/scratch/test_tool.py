import sys
from pathlib import Path

sys.path.insert(0, str(Path(r"d:\Python\nanobot")))

import asyncio
from nanobot.agent.tools.excel_actuator import ExcelActuatorTool
import logging

logging.basicConfig(level=logging.DEBUG)

async def main():
    workspace = Path(r"d:\Python\nanobot")
    tool = ExcelActuatorTool(workspace)
    print("Testing ExcelActuatorTool...")
    res = await tool.execute(
        file_path=r"D:\OneDrive - VR Management (Shanghai) Co., Ltd\Projects\European Data Validation\EURO DATA CUBE CONNECTION Sales & FF.xlsm",
        sheet_name="Occupancy Details",
        max_rows=15,
        max_cols=20
    )
    print("Result:")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
