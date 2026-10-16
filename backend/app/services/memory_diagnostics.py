"""Low overhead process memory readings for document-ingestion diagnostics."""

from pathlib import Path


def current_rss_mb() -> float | None:
    """Read resident memory from Linux procfs (available on Render)."""
    try:
        with Path("/proc/self/status").open(encoding="ascii") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def rss_log_value() -> str:
    """Format RSS consistently while keeping unsupported platforms explicit."""
    rss_mb = current_rss_mb()
    return f"{rss_mb:.1f}" if rss_mb is not None else "unavailable"
