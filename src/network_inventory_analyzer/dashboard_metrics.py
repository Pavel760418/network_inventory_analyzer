# -*- coding: utf-8 -*-
"""KPI и фактологические выводы. Пустой показатель не домысливается."""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.network_inventory_analyzer.category_reserve import reserve_total
from src.network_inventory_analyzer.settings import NON_CORE_SCOPES


def kpis(bundle: Dict[str, Any]) -> Dict[str, Any]:
    lines: pd.DataFrame = bundle["lines"]
    operational = lines[lines["include_in_production_score"] == True] if not lines.empty else lines  # noqa: E712
    household = lines[lines["scope"].isin(NON_CORE_SCOPES)] if not lines.empty else lines
    prices = bundle.get("prices", pd.DataFrame())
    posted = bundle.get("posted_full", pd.DataFrame())
    rating = bundle.get("rating", pd.DataFrame())
    risk_store = ""
    if rating is not None and not rating.empty:
        risk_store = str(rating.sort_values("чистые_недостачи", ascending=False).iloc[0]["магазин"])
    price_effect = None
    hh_sh = float(household["недостача_сумма"].sum()) if not household.empty else 0.0
    hh_sur = float(household["излишек_сумма"].sum()) if not household.empty else 0.0
    total_sh = float(lines["недостача_сумма"].sum()) if not lines.empty else 0.0
    total_sur = float(lines["излишек_сумма"].sum()) if not lines.empty else 0.0
    legacy = bundle.get("legacy_overlap", pd.DataFrame())
    applied = bundle.get("applied_pairs", pd.DataFrame())
    overlap_sum = 0.0
    if legacy is not None and not legacy.empty:
        overlap_sum += float(legacy["перекрытие_сум"].sum())
    if applied is not None and not applied.empty:
        overlap_sum += float(applied["перекрытие_сум"].sum())
    op_sh = float(operational["недостача_сумма"].sum()) if not operational.empty else 0.0
    return {
        "stores": int(lines["магазин"].nunique()) if not lines.empty else 0,
        "sku": int(lines["наименование"].nunique()) if not lines.empty else 0,
        "shortage": round(total_sh, 2),
        "surplus": round(total_sur, 2),
        "uncovered": round(max(op_sh - overlap_sum, 0), 2),
        "reserve": round(reserve_total(bundle.get("reserve", pd.DataFrame())), 2),
        "posted": round(float(posted["Сумма излишка"].sum()) if posted is not None and not posted.empty else 0.0, 2),
        "household_shortage": round(hh_sh, 2),
        "household_surplus": round(hh_sur, 2),
        "household_net": round(hh_sur - hh_sh, 2),
        "household_share_shortage": round(hh_sh / total_sh, 4) if total_sh else 0.0,
        "household_share_surplus": round(hh_sur / total_sur, 4) if total_sur else 0.0,
        "price_pairs": int(len(prices)) if prices is not None else 0,
        "price_effect": price_effect,
        "risk_store": risk_store,
        "lines": int(len(lines)),
    }


def conclusions(bundle: Dict[str, Any]) -> List[dict]:
    """Только наблюдаемые факты. Недостаток данных называется прямо."""
    lines: pd.DataFrame = bundle["lines"]
    out: List[dict] = []
    if lines is None or lines.empty:
        return [{"text": "Недостаточно данных для вывода.", "tab": "Главная", "amount": None}]

    op = lines[lines["include_in_shortage_top"] == True]  # noqa: E712
    shortages = op[op["недостача_сумма"] > 0].sort_values("недостача_сумма", ascending=False)
    if not shortages.empty:
        top = shortages.iloc[0]
        out.append(
            {
                "text": (
                    f"Крупнейшая недостача операционного контура: {top['наименование']} "
                    f"в «{top['магазин']}» на {float(top['недостача_сумма']):,.2f} ₽."
                ),
                "tab": "Недостачи",
                "amount": float(top["недостача_сумма"]),
            }
        )
    else:
        out.append({"text": "Недостаточно данных для вывода по недостачам операционного контура.", "tab": "Недостачи", "amount": None})

    rating = bundle.get("rating", pd.DataFrame())
    if rating is not None and not rating.empty:
        risk = rating.sort_values("чистые_недостачи", ascending=False).iloc[0]
        out.append(
            {
                "text": (
                    f"Наибольшие чистые недостачи операционного рейтинга: «{risk['магазин']}», "
                    f"{float(risk['чистые_недостачи']):,.2f} ₽, место {int(risk['место'])} "
                    f"(балл {risk['store_score']}, выше — лучше)."
                ),
                "tab": "Рейтинг магазинов",
                "amount": float(risk["чистые_недостачи"]),
            }
        )

    if "category_group" in op.columns and not op.empty:
        by_cat = op.groupby("category_group")["недостача_сумма"].sum().sort_values(ascending=False)
        if not by_cat.empty and float(by_cat.iloc[0]) > 0:
            out.append(
                {
                    "text": f"Категория с наибольшей недостачей контура: {by_cat.index[0]}, {float(by_cat.iloc[0]):,.2f} ₽.",
                    "tab": "Резерв категорий",
                    "amount": float(by_cat.iloc[0]),
                }
            )

    candidates = bundle.get("candidates", pd.DataFrame())
    if candidates is not None and not candidates.empty:
        row = candidates.sort_values("перекрытие_сум", ascending=False).iloc[0]
        out.append(
            {
                "text": (
                    f"Крупнейший кандидат на пересорт: {row['недостача_sku']} ↔ {row['излишек_sku']} "
                    f"в «{row['магазин']}», потенциал {float(row['перекрытие_сум']):,.2f} ₽. "
                    "Недостача этим кандидатом не уменьшена."
                ),
                "tab": "Пересорты и перекрытия",
                "amount": float(row["перекрытие_сум"]),
            }
        )
    else:
        out.append({"text": "Недостаточно данных для вывода по парам пересорта.", "tab": "Пересорты и перекрытия", "amount": None})

    unlinked = bundle.get("posted_unlinked", pd.DataFrame())
    if unlinked is not None and not unlinked.empty:
        row = unlinked.sort_values("Сумма излишка", ascending=False).iloc[0]
        out.append(
            {
                "text": (
                    f"Крупнейший несвязанный оприходованный излишек: {row['Наименование']} "
                    f"на {float(row['Сумма излишка']):,.2f} ₽. Причина не установлена."
                ),
                "tab": "Оприходованные излишки",
                "amount": float(row["Сумма излишка"]),
            }
        )
    else:
        out.append(
            {
                "text": "Недостаточно данных для вывода по оприходованным излишкам: файл закрытия смены не передан.",
                "tab": "Оприходованные излишки",
                "amount": None,
            }
        )

    prices = bundle.get("prices", pd.DataFrame())
    if prices is not None and not prices.empty:
        out.append(
            {
                "text": f"Ценовых пар между магазинами: {len(prices)}. Отдельный финансовый эффект отклонения в формуле v4 не задан.",
                "tab": "Аномалии цен",
                "amount": None,
            }
        )
    else:
        out.append({"text": "Недостаточно данных для вывода по аномалиям цен.", "tab": "Аномалии цен", "amount": None})

    kpi = bundle.get("kpi") or kpis(bundle)
    out.append(
        {
            "text": (
                f"Хозтовары, упаковка и тара вне операционного рейтинга: "
                f"недостачи {kpi['household_shortage']:,.2f} ₽, излишки {kpi['household_surplus']:,.2f} ₽."
            ),
            "tab": "Хозтовары и упаковка",
            "amount": kpi["household_shortage"],
        }
    )
    beef = bundle.get("beef_summary", pd.DataFrame())
    if beef is not None and not beef.empty:
        val = beef.iloc[0]["значение"]
        out.append(
            {
                "text": f"Подтверждённые недостачи говядины: {float(val):,.2f} ₽. Спорные позиции в эту сумму не входят.",
                "tab": "Говядина",
                "amount": float(val),
            }
        )
    out.append(
        {
            "text": "Первое действие: подтвердить или отклонить кандидатов пересорта и классификацию неразмеченных SKU.",
            "tab": "Контроль качества",
            "amount": None,
        }
    )
    return out[:10]
