import sys
import threading
import time
import pythoncom
import win32com.client
from pathlib import Path
from pywinauto import Desktop

file_path = r"D:\OneDrive - VR Management (Shanghai) Co., Ltd\Projects\European Data Validation\EURO DATA CUBE CONNECTION Sales & FF.xlsm"

def watchdog():
    print("Watchdog started...", flush=True)
    desktop = Desktop(backend="uia")
    start = time.time()
    seen = set()
    while time.time() - start < 180:
        try:
            for w in desktop.windows():
                title = w.window_text()
                if not title:
                    continue
                # Dump windows containing typical keywords
                if any(x in title.lower() for x in ["sign in", "microsoft", "account", "权限", "登录", "valueretail", "windows"]):
                    if title not in seen:
                        seen.add(title)
                        print(f"--- MATCHED WINDOW: {title} ---", flush=True)
                        w.print_control_identifiers()
                        print("---------------------------------", flush=True)
                        
                        # also try to look for the user email control
                        try:
                            # print just controls with email
                            for c in w.descendants():
                                if "dliu@valueretail.com" in c.window_text().lower() or "dliu@valueretail.com" in (c.element_info.name or "").lower():
                                    print(f"==> FOUND target control: {c.element_info.control_type} {c.element_info.name}", flush=True)
                        except Exception as e:
                            print(f"Error exploring descendants: {e}")
        except Exception as e:
            pass
        time.sleep(1)

t = threading.Thread(target=watchdog, daemon=True)
t.start()

pythoncom.CoInitialize()
try:
    xl = win32com.client.Dispatch("Excel.Application")
    xl.Visible = True
    xl.DisplayAlerts = False
    xl.AskToUpdateLinks = False

    print("Opening Excel...")
    wb = xl.Workbooks.Open(file_path, UpdateLinks=False, ReadOnly=False)
    print("Calling RefreshAll...")
    wb.RefreshAll()
    print("Waiting...")
    xl.CalculateUntilAsyncQueriesDone()
    print("Refreshed.")
except Exception as e:
    print(f"Error: {e}")
finally:
    try:
        if 'wb' in locals(): wb.Close(False)
    except: pass
    try:
        xl.Quit()
    except: pass
