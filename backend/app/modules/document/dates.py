"""Chronological sanity gate (DeepID team Reagvis)."""
from datetime import date, datetime


def parse(d: str | None) -> date | None:
    if not d:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(d.strip(), fmt).date()
        except ValueError:
            pass
    return None


def age_on(dob: date, on: date) -> float:
    return (on - dob).days / 365.25


def date_gate(dob_s: str | None, issue_s: str | None, today: date) -> list[str]:
    """Returns a list of violated rules (empty = pass)."""
    dob, issue = parse(dob_s), parse(issue_s)
    bad = []
    if dob is None:
        return ["dob_unreadable"]
    if dob > today:
        bad.append("dob_future")
    if issue and issue > today:
        bad.append("issue_future")
    if issue and dob >= issue:
        bad.append("dob_after_issue")
    a = age_on(dob, today)
    if not 18 <= a <= 100:
        bad.append("age_out_of_range")
    return bad


def test():
    t = date(2026, 10, 1)
    assert date_gate("01/01/1990", "01/01/2015", t) == []
    assert "dob_after_issue" in date_gate("01/01/2016", "01/01/2015", t)
    assert "age_out_of_range" in date_gate("01/01/2015", "01/01/2020", t)
    assert "issue_future" in date_gate("01/01/1990", "01/01/2030", t)


if __name__ == "__main__":
    test()
    print("dates ok")
