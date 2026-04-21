import sys
import os
from pathlib import Path

# Add tests directory to python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from tests.test_phase55_automated import test_phase55_no_print_in_host_agent, test_phase55_async_cancelled_error_guard
except ImportError as e:
    print(f"ImportError: {e}")
    sys.exit(1)

try:
    test_phase55_no_print_in_host_agent()
    print("NO_PRINT: OK")
except AssertionError as e:
    print("PRINT_VIOLATION:\n", e)

try:
    test_phase55_async_cancelled_error_guard()
    print("ASYNC_GUARD: OK")
except AssertionError as e:
    print("ASYNC_VIOLATION:\n", e)
