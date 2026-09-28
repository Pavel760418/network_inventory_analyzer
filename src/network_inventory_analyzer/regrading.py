# -*- coding: utf-8 -*-
"""Пересорты по справочнику пар. Кандидаты не уменьшают недостачу.

Формула перекрытия совпадает с действующим overlap: количество — минимум
остатков, сумма — минимум остатка суммы излишка и количества по цене недостачи.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from src.network_inventory_analyzer.related_pairs import find_pair_for_names, load_pairs, pair_decision
from src.network_inventory_analyzer.scope_classifier import production_mask
from src.network_inventory_analyzer.settings import STATUS_AUTO, STATUS_REVIEW


def _unit_price(qty: float, amount: float) -> float:
    if qty <= 0:
        return 0.0
    return amount / qty


def _legacy_cover(overlap: Optional[pd.DataFrame]) -> Dict[tuple, Dict[str, float]]:
    """Сколько количества и суммы уже закрыто действующим однородным перекрытием."""
    used: Dict[tuple, Dict[str, float]] = {}
    if overlap is None or overlap.empty:
        return used
    for _, row in overlap.iterrows():
        for kind, name_col, qty_col, sum_col in (
            ("излишек", "излишек_товар", "перекрытие_кол", "перекрытие_сум"),
            ("недостача", "недостача_товар", "перекрытие_кол", "перекрытие_сум"),
        ):
            store = str(row.get("магазин_изл" if kind == "излишек" else "магазин_нед", "") or "")
            name = str(row.get(name_col, "") or "")
            key = (kind, store, name)
            bucket = used.setdefault(key, {"qty": 0.0, "sum": 0.0})
            bucket["qty"] += float(row.get(qty_col, 0) or 0)
            bucket["sum"] += float(row.get(sum_col, 0) or 0)
    return used


def build_dictionary_regrades(
    df: pd.DataFrame,
    pairs: Optional[pd.DataFrame] = None,
    legacy_overlap: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    columns = [
        "pair_id", "магазин", "дата", "излишек_sku", "недостача_sku",
        "излишек_наименование", "недостача_наименование", "категория",
        "перекрытие_кол", "себестоимость_излишка", "себестоимость_недостачи",
        "разница_себестоимости", "перекрытие_сум", "уровень_связи",
        "тип_связи", "источник_правила", "статус", "пояснение",
        "уменьшает_недостачу",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    pairs = pairs if pairs is not None else load_pairs()
    work = df[production_mask(df, "include_in_regrading")].copy()
    if work.empty or pairs is None or pairs.empty:
        return pd.DataFrame(columns=columns)

    legacy = _legacy_cover(legacy_overlap)
    surplus_rows = []
    shortage_rows = []
    for idx, row in work.iterrows():
        store = str(row.get("магазин", ""))
        name = str(row.get("наименование", ""))
        if float(row.get("излишек_кол", 0) or 0) > 0:
            used = legacy.get(("излишек", store, name), {"qty": 0.0, "sum": 0.0})
            surplus_rows.append(
                {
                    "idx": idx,
                    "avail_qty": max(float(row["излишек_кол"]) - used["qty"], 0),
                    "avail_sum": max(float(row["излишек_сумма"]) - used["sum"], 0),
                }
            )
        if float(row.get("недостача_кол", 0) or 0) > 0:
            used = legacy.get(("недостача", store, name), {"qty": 0.0, "sum": 0.0})
            shortage_rows.append(
                {
                    "idx": idx,
                    "need_qty": max(float(row["недостача_кол"]) - used["qty"], 0),
                    "need_sum": max(float(row["недостача_сумма"]) - used["sum"], 0),
                }
            )
    sur = {item["idx"]: item for item in surplus_rows}
    sh = {item["idx"]: item for item in shortage_rows}

    candidates: List[dict] = []
    for s_idx, s_state in sur.items():
        srow = work.loc[s_idx]
        for d_idx, d_state in sh.items():
            drow = work.loc[d_idx]
            if str(srow.get("магазин", "")) != str(drow.get("магазин", "")):
                continue
            found = find_pair_for_names(
                str(drow.get("наименование", "")),
                str(srow.get("наименование", "")),
                str(drow.get("артикул", "")),
                str(srow.get("артикул", "")),
                pairs,
            )
            if found is None:
                continue
            try:
                priority = int(float(found.get("priority") or 100))
            except ValueError:
                priority = 100
            candidates.append((priority, -float(drow.get("недостача_сумма", 0) or 0), s_idx, d_idx, found))

    candidates.sort(key=lambda item: (item[0], item[1]))
    result = []
    for _, _, s_idx, d_idx, found in candidates:
        srow = work.loc[s_idx]
        drow = work.loc[d_idx]
        status = pair_decision(found)
        s_price = _unit_price(float(srow["излишек_кол"]), float(srow["излишек_сумма"]))
        d_price = _unit_price(float(drow["недостача_кол"]), float(drow["недостача_сумма"]))
        if status == STATUS_AUTO:
            cover_qty = min(sur[s_idx]["avail_qty"], sh[d_idx]["need_qty"])
            if cover_qty <= 0:
                continue
            cover_sum = min(
                sur[s_idx]["avail_sum"],
                round(cover_qty * d_price, 2) if d_price > 0 else sh[d_idx]["need_sum"],
            )
            if cover_sum <= 0:
                continue
            sur[s_idx]["avail_qty"] = round(sur[s_idx]["avail_qty"] - cover_qty, 6)
            sur[s_idx]["avail_sum"] = round(sur[s_idx]["avail_sum"] - cover_sum, 2)
            sh[d_idx]["need_qty"] = round(sh[d_idx]["need_qty"] - cover_qty, 6)
            sh[d_idx]["need_sum"] = round(max(sh[d_idx]["need_sum"] - cover_sum, 0), 2)
            reduces = True
            note = "Пара подтверждена в справочнике и уменьшает недостачу в пределах остатка."
        elif status == STATUS_REVIEW:
            cover_qty = min(float(srow["излишек_кол"]), float(drow["недостача_кол"]))
            cover_sum = round(cover_qty * d_price, 2) if d_price > 0 else 0.0
            reduces = False
            note = (
                "Кандидат на пересорт. Недостача не уменьшена: связь требует ручного подтверждения. "
                "Потенциал показан справочно и не суммируется в ущерб."
            )
        else:
            cover_qty = 0.0
            cover_sum = 0.0
            reduces = False
            note = "Пара отклонена справочником и не участвует в перекрытии."
        result.append(
            {
                "pair_id": found.get("pair_id", ""),
                "магазин": srow.get("магазин", ""),
                "дата": srow.get("дата_док", ""),
                "излишек_sku": srow.get("наименование", ""),
                "недостача_sku": drow.get("наименование", ""),
                "излишек_наименование": srow.get("наименование", ""),
                "недостача_наименование": drow.get("наименование", ""),
                "категория": drow.get("category_group", ""),
                "перекрытие_кол": round(float(cover_qty), 3),
                "себестоимость_излишка": round(s_price, 2),
                "себестоимость_недостачи": round(d_price, 2),
                "разница_себестоимости": round(abs(s_price - d_price) * float(cover_qty), 2),
                "перекрытие_сум": round(float(cover_sum), 2),
                "уровень_связи": found.get("match_level", ""),
                "тип_связи": found.get("relationship_type", ""),
                "источник_правила": found.get("source", ""),
                "статус": status,
                "пояснение": note,
                "уменьшает_недостачу": reduces,
            }
        )
    return pd.DataFrame(result, columns=columns)


def applied_regrades(regrades: pd.DataFrame) -> pd.DataFrame:
    if regrades is None or regrades.empty:
        return pd.DataFrame(columns=getattr(regrades, "columns", []))
    return regrades[regrades["уменьшает_недостачу"] == True].copy()  # noqa: E712


def candidate_regrades(regrades: pd.DataFrame) -> pd.DataFrame:
    if regrades is None or regrades.empty:
        return pd.DataFrame(columns=getattr(regrades, "columns", []))
    return regrades[regrades["статус"] == STATUS_REVIEW].copy()
