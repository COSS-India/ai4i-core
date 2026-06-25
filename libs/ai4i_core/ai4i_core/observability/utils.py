import time


def compute_total_time_ms(start_time: float) -> float:
    """Compute elapsed time in milliseconds from a time.time() start."""
    return round((time.time() - start_time) * 1000, 2)





