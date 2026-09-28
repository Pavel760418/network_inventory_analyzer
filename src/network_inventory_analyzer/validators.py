# -*- coding: utf-8 -*-
"""Проверки справочников и инвариантов перекрытия."""
from __future__ import annotations

from typing import List

import pandas as pd

from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import AUTO_PAIR_TYPES


REQUIRED_PAIR_COLUMNS = [
    "pair_id",
    "product_a_name",
    "product_b_name",
    "relationship_type",
    "active",
]


def validate_pairs(pairs: pd.DataFrame) -> List[str]:
    issues: List[str] = []
    if pairs is None or pairs.empty:
        issues.append("Справочник пар пуст. Автоматических пересортов нет.")
        return issues
    missing = [c for c in REQUIRED_PAIR_COLUMNS if c not in pairs.columns]
    if missing:
        issues.append("В справочнике пар нет колонок: " + ", ".join(missing))
        return issues
    for _, row in pairs.iterrows():
        a = norm_txt(row.get("product_a_name", ""))
        b = norm_txt(row.get("product_b_name", ""))
        if a and a == b:
            issues.append(f"Самопара {row.get('pair_id')}: названия совпадают, пара не используется.")
        rel = str(row.get("relationship_type", "")).strip()
        if rel and rel not in AUTO_PAIR_TYPES and rel != "requires_manual_review":
            issues.append(f"Неизвестный тип связи {rel} у {row.get('pair_id')}. Пара потребует ручной проверки.")
    return issues


def allocation_ok(applied: pd.DataFrame, lines: pd.DataFrame) -> List[str]:
    """Излишек не расходуется сверх количества, недостача не закрывается более чем на 100%."""
    issues: List[str] = []
    if applied is None or applied.empty:
        return issues
    if "перекрытие_кол" not in applied.columns:
        return issues
    sur = applied.groupby(["магазин", "излишек_sku"], dropna=False)["перекрытие_кол"].sum()
    sh = applied.groupby(["магазин", "недостача_sku"], dropna=False)["перекрытие_кол"].sum()
    qty_sur = lines.groupby(["магазин", "наименование"])["излишек_кол"].sum()
    qty_sh = lines.groupby(["магазин", "наименование"])["недостача_кол"].sum()
    for key, used in sur.items():
        avail = float(qty_sur.get(key, 0) or 0)
        if used - avail > 1e-6:
            issues.append(f"Излишек {key} перекрыт на {used}, доступно {avail}.")
    for key, used in sh.items():
        need = float(qty_sh.get(key, 0) or 0)
        if used - need > 1e-6:
            issues.append(f"Недостача {key} закрыта на {used}, при количестве {need}.")
    return issues
