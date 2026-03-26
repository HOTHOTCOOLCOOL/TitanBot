"""
Sandbox Worker Script for Python Plugin Execution (Phase 28B).
This script executes untrusted `hooks.py` modules inside an isolated subprocess
with a strict sys.addaudithook monitoring layer.
"""

import sys
import json
import os
import ast
import traceback
from pathlib import Path
import importlib.util


def install_audit_hook(workspace_path: str, allow_network: bool):
    """Installs a strict sys.addaudithook to prevent dangerous operations."""
    workspace = Path(workspace_path).resolve()
    
    def audit_hook(event, args):
        # 1. Block Subprocess Creation
        if event in ("os.system", "os.exec", "os.spawn", "os.posix_spawn", "subprocess.Popen"):
            raise PermissionError(f"Sandbox Violation: Subprocess execution is blocked ({event})")
            
        # 2. Block Network Connections if not allowed
        if not allow_network and event in ("socket.bind", "socket.connect", "urllib.Request"):
            raise PermissionError(f"Sandbox Violation: Network access is blocked ({event})")
            
        # 3. Block writing outside of workspace
        if event == "open" and len(args) >= 2:
            file_path, mode = args[0], args[1]
            if isinstance(mode, str) and ("w" in mode or "a" in mode or "+" in mode):
                try:
                    target_path = Path(file_path).resolve()
                    if not str(target_path).startswith(str(workspace)):
                        # Allow temp files needed by python runtime sometimes, or stdout
                        if not target_path.exists() and "tmp" not in str(target_path).lower() and "temp" not in str(target_path).lower():
                            raise PermissionError(f"Sandbox Violation: Write access outside workspace blocked ({file_path})")
                except Exception as e:
                    if isinstance(e, PermissionError):
                        raise
                    pass # Ignore resolution errors for virtual files like NUL
                    
    sys.addaudithook(audit_hook)


def process_request():
    """Main execution entry point."""
    if len(sys.argv) < 3:
        sys.stderr.write("Usage: sandbox_worker.py <hooks_file> <hook_name>")
        sys.exit(1)
        
    hooks_file = Path(sys.argv[1])
    hook_name = sys.argv[2]
    
    # Read payload from stdin
    try:
        payload_data = sys.stdin.read()
        payload = json.loads(payload_data)
    except Exception as e:
        sys.stderr.write(f"Failed to read payload: {e}")
        sys.exit(1)
        
    context = payload.get("context", {})
    result_content = payload.get("result", None)
    workspace = payload.get("workspace", os.getcwd())
    allow_network = payload.get("allow_network", False)
    
    # Python 3 asyncio handling inside worker - Initialize BEFORE audit hook
    # to avoid Windows ProactorEventLoop internal socket.bind triggering sandbox violation
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    # Install the security hooks
    install_audit_hook(workspace, allow_network)
    
    try:
        # Load the module
        spec = importlib.util.spec_from_file_location("sandbox_hook", str(hooks_file))
        if not spec or not spec.loader:
            raise ImportError(f"Cannot load module from {hooks_file}")
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Execute the hook
        if not hasattr(module, hook_name):
            # Hook not present, just return success
            print(json.dumps({"success": True, "message": ""}))
            sys.exit(0)
            
        hook_func = getattr(module, hook_name)
        
        if hook_name == "pre_execute":
            # await module.pre_execute(context)
            if asyncio.iscoroutinefunction(hook_func):
                hook_result = loop.run_until_complete(hook_func(context))
            else:
                hook_result = hook_func(context)
                
            if isinstance(hook_result, dict):
                print(json.dumps({"success": True, "result": hook_result}))
            else:
                print(json.dumps({"success": True}))
                
        elif hook_name == "post_execute":
            # await module.post_execute(context, result)
            if asyncio.iscoroutinefunction(hook_func):
                loop.run_until_complete(hook_func(context, result_content))
            else:
                hook_func(context, result_content)
                
            print(json.dumps({"success": True}))
            
        loop.close()
        
    except Exception as e:
        # Format the exception and print to stderr
        err_msg = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        sys.stderr.write(err_msg)
        sys.exit(1)


if __name__ == "__main__":
    process_request()
