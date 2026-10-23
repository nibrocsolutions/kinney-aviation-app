from datetime import date


def days_until(due: date | None, today: date) -> int | None:
    if due is None:
        return None
    return (due - today).days


def annual_is_due(due: date | None, today: date, window_days: int) -> bool:
    remaining = days_until(due, today)
    return remaining is not None and remaining <= window_days
