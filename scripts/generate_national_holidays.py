"""Generate dbt/seeds/feriados_nacionais.csv (RF-03, task 3.2).

Brazilian national holidays that close the financial market, built from the rules in law
instead of a downloaded calendar, so the seed is reproducible:

- fixed dates: Lei 662/1949 (as amended by Lei 10.607/2002), Lei 6.802/1980 (12 Oct) and,
  from 2024, Lei 14.759/2023 (20 Nov);
- Easter-based: Carnival Monday and Tuesday, Good Friday and Corpus Christi, which are not
  federal holidays by law but are non-business days in the national financial calendar
  (ANBIMA / B3).

Limits: no state or municipal holidays, no one-off closures decreed for a single year.

Usage: python scripts/generate_national_holidays.py [first_year] [last_year]
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "feriados_nacionais.csv"

FIXED: list[tuple[int, int, str]] = [
    (1, 1, "Confraternizacao Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalho"),
    (9, 7, "Independencia do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamacao da Republica"),
    (12, 25, "Natal"),
]


def easter(year: int) -> date:
    """Easter Sunday (anonymous Gregorian algorithm, Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return date(year, month, day + 1)


def holidays(year: int) -> list[tuple[date, str, str]]:
    rows = [(date(year, m, d), name, "FIXO") for m, d, name in FIXED]
    if year >= 2024:
        rows.append((date(year, 11, 20), "Dia Nacional de Zumbi e da Consciencia Negra", "FIXO"))
    sunday = easter(year)
    rows += [
        (sunday - timedelta(days=48), "Carnaval (segunda-feira)", "MOVEL"),
        (sunday - timedelta(days=47), "Carnaval (terca-feira)", "MOVEL"),
        (sunday - timedelta(days=2), "Paixao de Cristo", "MOVEL"),
        (sunday + timedelta(days=60), "Corpus Christi", "MOVEL"),
    ]
    return rows


def main(first_year: int = 2000, last_year: int = 2035) -> None:
    rows = sorted(r for y in range(first_year, last_year + 1) for r in holidays(y))
    lines = ["dt_feriado,nm_feriado,tp_feriado"]
    lines += [f"{dt.isoformat()},{name},{kind}" for dt, name, kind in rows]
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(rows)} holidays written to {OUTPUT}")


if __name__ == "__main__":
    main(*(int(arg) for arg in sys.argv[1:3]))
