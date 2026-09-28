# -*- coding: utf-8 -*-
"""Контроль полноты: строк в отчёте столько же, сколько в расчётном наборе."""
from __future__ import annotations

from typing import Iterable, Tuple

import pandas as pd


def completeness_row(name: str, source_rows: int, report_rows: int, reason: str = "") -> dict:
    clipped = report_rows != source_rows
    if not clipped:
        status = "OK"
    elif reason:
        status = "исключение"
    else:
        status = "ОБРЕЗАНО"
    return {
        "Таблица": name,
        "Строк в источнике": int(source_rows),
        "Строк в полном отчёте": int(report_rows),
        "Обрезано": "да" if clipped else "нет",
        "Причина": reason,
        "Статус": status if clipped else "OK",
    }


def build_completeness(pairs: Iterable[Tuple[str, pd.DataFrame, pd.DataFrame, str]]) -> pd.DataFrame:
    rows = []
    for name, source, report, reason in pairs:
        src_n = 0 if source is None else len(source)
        rep_n = 0 if report is None else len(report)
        rows.append(completeness_row(name, src_n, rep_n, reason))
    return pd.DataFrame(rows)
