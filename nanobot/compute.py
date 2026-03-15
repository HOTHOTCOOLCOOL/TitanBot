"""Compute Broker for Nanobot.

Provides a global ProcessPoolExecutor to offload CPU-bound tasks
(like PDF/Excel parsing, heavy data manipulation) out of the main asyncio
event loop to prevent blocking the heartbeat and message processing.
"""

import asyncio
import concurrent.futures
from loguru import logger
from typing import Callable, Any

class ComputeBroker:
    """Singleton broker for CPU-heavy tasks."""
    _instance = None
    _executor: concurrent.futures.ProcessPoolExecutor | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ComputeBroker, cls).__new__(cls)
            cls._instance._init_executor()
        return cls._instance

    def _init_executor(self):
        # Initialize a process pool.
        # Max workers defaults to the number of processors on the machine.
        # We can limit it if we want to save memory.
        self._executor = concurrent.futures.ProcessPoolExecutor()
        logger.info(f"Initialized ComputeBroker")

    async def run_cpu_heavy(self, func: Callable[..., Any], *args: Any) -> Any:
        """Run a CPU-heavy function in the process pool.
        
        Args:
            func: The pure, un-bound function to execute. MUST be picklable
                  (i.e., defined at the top-level of a module, not a method or lambda).
            args: Arguments to pass to the function. MUST be picklable.
            
        Returns:
            The result of the function execution.
        """
        if self._executor is None:
            # Fallback: run synchronously if pool was shut down (graceful degradation)
            logger.warning(f"ComputeBroker executor is shut down, running {func.__name__} synchronously")
            return func(*args)
            
        loop = asyncio.get_running_loop()
        
        # loguru logger is picklable, but passing logger objects is risky.
        # We keep the function signatures clean (primitives in, primitives out).
        try:
            return await loop.run_in_executor(self._executor, func, *args)
        except Exception as e:
            logger.error(f"Error in ComputeBroker task {func.__name__}: {e}")
            raise

    def shutdown(self, wait=True):
        """Shutdown the process pool."""
        if self._executor:
            logger.info("Shutting down ComputeBroker...")
            self._executor.shutdown(wait=wait)
            self._executor = None
        ComputeBroker._instance = None  # Allow re-initialization if needed

# Global helper function for ease of use
async def run_cpu_heavy(func: Callable[..., Any], *args: Any) -> Any:
    """Helper method to run tasks dynamically via the singleton broker."""
    broker = ComputeBroker()
    return await broker.run_cpu_heavy(func, *args)

def shutdown_broker(wait=True):
    broker = ComputeBroker()
    broker.shutdown(wait=wait)
