#!/usr/bin/env python3
"""tidewatch.py — the tide reader as a script (twin of a Python source)."""
import csv
import sys
from datetime import datetime


def load(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main(argv):
    rows = load(argv[1])
    now = datetime.now()
    for r in rows:
        if datetime.fromisoformat(f"{r['date']}T{r['time']}") >= now:
            print(f"{r['kind']:5} {r['time']}  {float(r['height']):.1f} m")
            break


if __name__ == "__main__":
    main(sys.argv)
