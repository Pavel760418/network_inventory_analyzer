# -*- coding: utf-8 -*-
"""Оприходованные излишки: связанные, кандидаты, несвязанные.

Причина несвязанной позиции — гипотеза, не установленный факт.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import HYPOTHESIS_PREFIX, STATUS_REVIEW


def analyze_posted(
    cap: Optional[pd.DataFrame],
    lines: pd.DataFrame,
    regrades: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    columns = [
        "Магазин", "SKU", "Наименование", "Категория", "Количество",
        "Себестоимость", "Сумма излишка", "Тип связи",
        "Связанная недостача / SKU", "pair_id", "Сумма перекрытия",
        "Уровень подтверждения", "Гипотеза причины",
        "Ответственный за проверку", "Рекомендованное действие", "Статус расследования",
    ]
    empty = pd.DataFrame(columns=columns)
    if cap is None or cap.empty:
        note = empty.copy()
        return {
            "summary": pd.DataFrame([{"группа": "нет файла оприходования", "строк": 0, "сумма": 0.0}]),
            "linked": empty,
            "candidates": empty,
            "unlinked": empty,
            "hypotheses": note,
            "full": empty,
        }

    review_names = set()
    if regrades is not None and not regrades.empty:
        review = regrades[regrades["статус"] == STATUS_REVIEW]
        review_names = set(norm_txt(x) for x in review["излишек_sku"].astype(str))

    rows = []
    for _, row in cap.iterrows():
        name = str(row.get("наименование", "") or "")
        store = str(row.get("магазин", "") or row.get("склад", "") or "")
        qty = float(row.get("оп_количество", row.get("количество", 0)) or 0)
        amount = float(row.get("оп_сумма", row.get("сумма", 0)) or 0)
        status = str(row.get("status", row.get("статус", "")) or "")
        inv_shortage = float(row.get("inv_shortage", row.get("недостача_инвентаризации", 0)) or 0)
        category = ""
        if not lines.empty and "наименование" in lines.columns:
            hit = lines[lines["наименование"].astype(str) == name]
            if not hit.empty:
                category = str(hit.iloc[0].get("category_group", ""))
        unit = (amount / qty) if qty else 0.0
        if "shortage" in status or inv_shortage > 0:
            group = "A"
            link = "недостача того же наименования в инвентаризации"
            pair_id = ""
            cover = min(amount, inv_shortage) if inv_shortage else amount
            level = "точное имя и недостача в том же магазине"
            hypothesis = ""
            action = "Сверить пересорт и документы перемещения."
            invest = "связано"
        elif norm_txt(name) in review_names:
            group = "B"
            link = "кандидат справочника пар"
            pair_id = ""
            cover = 0.0
            level = "требует ручной проверки"
            hypothesis = ""
            action = "Подтвердить или отклонить пару. Сумму недостачи не уменьшать."
            invest = "кандидат"
        else:
            group = "C"
            link = ""
            pair_id = ""
            cover = 0.0
            level = "связи нет"
            hypothesis = _hypothesis(row, qty, amount)
            action = "Передать на проверку. Гипотезу не проводить в учёт."
            invest = "не связано"
        rows.append(
            {
                "Магазин": store,
                "SKU": name,
                "Наименование": name,
                "Категория": category,
                "Количество": qty,
                "Себестоимость": round(unit, 2),
                "Сумма излишка": round(amount, 2),
                "Тип связи": {"A": "связано с недостачей", "B": "кандидат", "C": "не связано"}[group],
                "Связанная недостача / SKU": link,
                "pair_id": pair_id,
                "Сумма перекрытия": round(cover, 2) if group == "A" else 0.0,
                "Уровень подтверждения": level,
                "Гипотеза причины": hypothesis,
                "Ответственный за проверку": "служба контроля",
                "Рекомендованное действие": action,
                "Статус расследования": invest,
                "_group": group,
            }
        )
    full = pd.DataFrame(rows)
    summary = (
        full.groupby("Тип связи", dropna=False)
        .agg(строк=("SKU", "size"), сумма=("Сумма излишка", "sum"))
        .reset_index()
        .rename(columns={"Тип связи": "группа"})
    )
    return {
        "summary": summary,
        "linked": full[full["_group"] == "A"].drop(columns="_group"),
        "candidates": full[full["_group"] == "B"].drop(columns="_group"),
        "unlinked": full[full["_group"] == "C"].drop(columns="_group"),
        "hypotheses": full[full["_group"] == "C"][
            ["Магазин", "Наименование", "Сумма излишка", "Гипотеза причины", "Рекомендованное действие"]
        ],
        "full": full.drop(columns="_group"),
    }


def _hypothesis(row: pd.Series, qty: float, amount: float) -> str:
    if qty and amount == 0:
        reason = "ошибка цены/себестоимости"
    elif qty == 0 and amount:
        reason = "ошибка единицы измерения"
    else:
        reason = "прочее / требует расследования"
    return f"{HYPOTHESIS_PREFIX}: {reason}"
