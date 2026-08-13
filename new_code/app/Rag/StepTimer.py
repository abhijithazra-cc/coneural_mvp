import time
import logging

logger = logging.getLogger("ask_timing")

class StepTimer:
    """Tracks elapsed time per named step + running total."""
    def __init__(self, name="ask"):
        self.name = name
        self.start = time.monotonic()
        self.last = self.start
        self.steps = []

    def mark(self, label):
        now = time.monotonic()
        elapsed = now - self.last
        total = now - self.start
        self.steps.append((label, elapsed, total))
        self.last = now
        logger.info("[%s] %-35s %8.3fs (total %8.3fs)", self.name, label, elapsed, total)
        return elapsed

    def summary(self):
        lines = [f"[{self.name}] --- timing summary ---"]
        for label, elapsed, total in self.steps:
            lines.append(f"  {label:<35} {elapsed:>8.3f}s  (total {total:>8.3f}s)")
        return "\n".join(lines)