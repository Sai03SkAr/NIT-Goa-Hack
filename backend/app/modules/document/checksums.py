import re

# Verhoeff tables (same checksum family as Aadhaar)
_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(num: str) -> bool:
    digits = re.sub(r"\D", "", num or "")
    if len(digits) != 12 or digits[0] in "01":
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(num11: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num11)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def pan_valid(pan: str, surname: str) -> tuple[bool, str]:
    """Format + 4th char holder type 'P' (person) + 5th char = surname initial."""
    pan = (pan or "").upper().strip()
    if not PAN_RE.match(pan):
        return False, "format"
    if pan[3] != "P":
        return False, "holder_type"
    if surname and pan[4] != surname.strip()[:1].upper():
        return False, "surname_initial"
    return True, "ok"


def test():
    import random
    for _ in range(200):
        n11 = str(random.randint(2, 9)) + "".join(random.choice("0123456789") for _ in range(10))
        full = n11 + verhoeff_digit(n11)
        assert verhoeff_valid(full), full
        bad = full[:-1] + str((int(full[-1]) + 1) % 10)
        assert not verhoeff_valid(bad)
    assert pan_valid("ABCPK1234Z", "Kumar") == (True, "ok")
    assert pan_valid("ABCCK1234Z", "Kumar")[1] == "holder_type"


if __name__ == "__main__":
    test()
    print("checksums ok")
