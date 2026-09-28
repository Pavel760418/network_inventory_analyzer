# -*- coding: utf-8 -*-
"""Резерв категории — потенциальный остаток, не фактическая экономия.

Допустимое перекрытие = min(недостача категории, излишки категории)
Неперекрытая недостача = max(недостача − факт перекрытия, 0)
Резерв = max(допустимое перекрытие − факт перекрытия, 0)

Факт перекрытия — только однородное перекрытие v4 и автоматически
подтверждённые пары справочника. Кандидаты в факт не входят.
Резерв не вычитается из чистой недостачи.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from src.network_inventory_analyzer.scope_classifier import production_mask

METHOD = (
    "Допустимое перекрытие = min(недостача, излишки) внутри категории и контура. "
    "Резерв = max(допустимое перекрытие − уже применённое перекрытие, 0). "
    "Единица: рубли. Это потолок неиспользованного однокатегорийного излишка, "
    "а не подтверждённая экономия."
)


def category_reserve(
    df: pd.DataFrame,
    legacy_overlap: Optional[pd.DataFrame] = None,
    applied_pairs: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    columns = [
        "Категория", "Недостача, ₽", "Излишки, ₽", "Допустимое перекрытие, ₽",
        "Неперекрытая недостача, ₽", "Резерв, ₽", "Метод расчёта",
        "Ограничение", "Комментарий", "Источник", "Статус",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    work = df[production_mask(df, "include_in_production_score")].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)
    if "category_group" not in work.columns:
        work["category_group"] = "Без категории"
    work["category_group"] = work["category_group"].replace("", "Без категории").fillna("Без категории")

    applied = {}
    if legacy_overlap is not None and not legacy_overlap.empty and "category_group" in legacy_overlap.columns:
        for cat, grp in legacy_overlap.groupby(legacy_overlap["category_group"].fillna("Без категории")):
            applied[str(cat)] = applied.get(str(cat), 0.0) + float(grp["перекрытие_сум"].sum())
    if applied_pairs is not None and not applied_pairs.empty:
        for cat, grp in applied_pairs.groupby(applied_pairs["категория"].fillna("Без категории")):
            applied[str(cat)] = applied.get(str(cat), 0.0) + float(grp["перекрытие_сум"].sum())

    rows = []
    for cat, grp in work.groupby("category_group"):
        shortage = float(grp["недостача_сумма"].sum())
        surplus = float(grp["излишек_сумма"].sum())
        allowable = min(shortage, surplus)
        fact = min(float(applied.get(str(cat), 0.0)), shortage)
        uncovered = max(shortage - fact, 0.0)
        reserve = max(allowable - fact, 0.0)
        rows.append(
            {
                "Категория": cat,
                "Недостача, ₽": round(shortage, 2),
                "Излишки, ₽": round(surplus, 2),
                "Допустимое перекрытие, ₽": round(allowable, 2),
                "Неперекрытая недостача, ₽": round(uncovered, 2),
                "Резерв, ₽": round(reserve, 2),
                "Метод расчёта": METHOD,
                "Ограничение": (
                    "Резерв не равен экономии. Межкатегорийные пары справочника сюда не входят. "
                    "Кандидаты requires_manual_review резерв не создают и недостачу не уменьшают."
                ),
                "Комментарий": "Требует ручной проверки, если резерв больше нуля.",
                "Источник": "строки инвентаризации + перекрытие v4 + подтверждённые пары",
                "Статус": "рассчитано",
            }
        )
    out = pd.DataFrame(rows, columns=columns)
    return out.sort_values("Резерв, ₽", ascending=False)


def reserve_total(reserve: pd.DataFrame) -> float:
    if reserve is None or reserve.empty:
        return 0.0
    return float(reserve["Резерв, ₽"].sum())
