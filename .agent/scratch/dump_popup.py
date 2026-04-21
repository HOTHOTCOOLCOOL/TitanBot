import time
from pywinauto import Desktop

desktop = Desktop(backend="uia")
for w in desktop.windows():
    title = w.window_text()
    if not title or "Outlook" in title or "Chrome" in title or "Firefox" in title or len(title) > 60:
        continue
        
    lower_title = title.lower()
    if any(k in lower_title for k in ["sign in", "microsoft", "account", "权限", "登录", "valueretail", "windows", "安全", "excel"]):
        print(f"\n--- MATCHED WINDOW: {title} ---")
        try:
            w.print_control_identifiers(depth=3)
        except Exception as e:
            print(f"Error exploring: {e}")
