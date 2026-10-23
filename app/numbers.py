from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session


def next_number(db: Session, column, prefix: str, on: date | None = None) -> str:
    year = (on or date.today()).year
    stem = f"{prefix}-{year}-"
    existing = db.scalars(select(column).where(column.like(f"{stem}%"))).all()
    highest = 0
    for number in existing:
        tail = str(number).rsplit("-", 1)[-1]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{stem}{highest + 1:03d}"
