"""Content-free measurements of this Python process, not the host/container."""

import sys
import time
from pathlib import Path

try:
    import resource
except ImportError:
    resource = None

_STARTED = time.monotonic()


def process_metrics():
    current_rss = None
    peak_rss = None
    if sys.platform.startswith("linux"):
        try:
            current_rss = next(
                int(line.split()[1]) * 1024
                for line in Path("/proc/self/smaps_rollup").read_text().splitlines()
                if line.startswith("Rss:")
            )
        except (OSError, ValueError, IndexError, StopIteration):
            pass
    if resource is not None:
        try:
            value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak_rss = int(value if sys.platform == "darwin" else value * 1024)
        except (OSError, ValueError):
            pass
    return {
        "scope": "python_process_only",
        "sampled_at": time.time(),
        "observation_elapsed_seconds": round(time.monotonic() - _STARTED, 6),
        "cpu_clock_seconds": round(time.process_time(), 6),
        "current_rss_bytes": current_rss,
        "peak_rss_bytes": peak_rss,
    }
