"""Indian-name-aware fuzzy matching (initials, Mohd/Mohammed, common transliteration swaps)."""
import re

from rapidfuzz.distance import JaroWinkler
from rapidfuzz import fuzz

ALIASES = {"MOHD": "MOHAMMED", "MD": "MOHAMMED", "MOHAMMAD": "MOHAMMED", "MUHAMMAD": "MOHAMMED",
           "SK": "SHAIKH", "SHEIKH": "SHAIKH", "KUMARI": "KUMARI"}
SWAPS = [("EE", "I"), ("OO", "U"), ("SH", "S"), ("W", "V"), ("AA", "A"), ("TH", "T"), ("PH", "F")]


def norm_token(t: str) -> str:
    t = ALIASES.get(t, t)
    for a, b in SWAPS:
        t = t.replace(a, b)
    return t.rstrip("A") or t


def tokens(name: str) -> list[str]:
    return [norm_token(t) for t in re.sub(r"[^A-Z ]", " ", (name or "").upper()).split()]


def name_sim(a: str, b: str) -> float:
    """0..1. Initials count as matches ('R. KUMAR' ~ 'RAHUL KUMAR')."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if len(ta) == len(tb):
        s = []
        for x, y in zip(ta, tb):
            if len(x) == 1 or len(y) == 1:
                s.append(0.92 if x[0] == y[0] else 0.0)
            else:
                s.append(JaroWinkler.similarity(x, y))
        aligned = sum(s) / len(s)
    else:
        aligned = 0.0
    return max(aligned, fuzz.token_sort_ratio(" ".join(ta), " ".join(tb)) / 100)


def email_stem(email: str) -> tuple[str, int | None]:
    local = (email or "").split("@")[0].lower()
    digits = re.findall(r"\d+", local)
    stem = re.sub(r"[\d._\-+]", "", local)
    return stem, int(digits[-1]) if digits else None


def test():
    assert name_sim("R. Kumar", "Rahul Kumar") > .9
    assert name_sim("Mohd Arif", "Mohammed Arif") > .95
    assert name_sim("Sushil Sharma", "Susil Sarma") > .9
    assert name_sim("Rahul Kumar", "Priya Nair") < .6
    assert email_stem("rahul.k12@gmail.com") == ("rahulk", 12)


if __name__ == "__main__":
    test()
    print("fuzzy ok")
