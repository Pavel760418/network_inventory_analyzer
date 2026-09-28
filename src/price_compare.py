# -*- coding: utf-8 -*-
"""Cross-store book PRICE comparison by exact product name (Release 4).

Pipeline:
1) find intersecting names (exact match across 2+ stores);
2) for each store+name compute unit prices:
     цена_нормативная = сумма_учетная / кол_учетное
     цена_фактическая = сумма_факт / кол_факт
   (only rows with qty > 0 and non-missing book sum);
3) pairwise compare prices between stores (never mix store rows).

Sums themselves are NOT compared — only unit prices.
"""
from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.text_normalize import price_per_unit

# Relative gap thresholds for status (on unit prices)
GAP_OK = 0.01          # <=1% — совпадает
GAP_NOTICE = 0.05      # <=5% — незначительное
GAP_WARN = 0.15        # <=15% — заметное
# >15% — требует проверки

STATUS_OK = "совпадает"
STATUS_MINOR = "незначительное расхождение"
STATUS_NOTICE = "заметное отклонение"
STATUS_CHECK = "требует проверки"
STATUS_NO_PRICE = "нет цены для сравнения"


def unit_price(qty: float, amount: float) -> Optional[float]:
    """Цена = сумма / количество. None if cannot compute."""
    try:
        q = float(qty)
        s = float(amount)
    except (TypeError, ValueError):
        return None
    if q != q or s != s:  # NaN
        return None
    if q <= 0:
        return None
    if s < 0:
        return None
    return price_per_unit(q, s)


def _gap_pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    if a == 0 and b == 0:
        return 0.0
    base = max(abs(a), abs(b))
    if base == 0:
        return 0.0
    return abs(a - b) / base


def _status_from_gap(gap: Optional[float]) -> str:
    if gap is None:
        return STATUS_NO_PRICE
    if gap <= GAP_OK:
        return STATUS_OK
    if gap <= GAP_NOTICE:
        return STATUS_MINOR
    if gap <= GAP_WARN:
        return STATUS_NOTICE
    return STATUS_CHECK


def _agg_qty_sum_price(
    grp: pd.DataFrame,
    qty_col: str,
    sum_col: str,
    missing_col: str,
) -> Tuple[float, float, Optional[float]]:
    """Aggregate valid rows → (qty_total, sum_total, unit_price).

    Excludes missing-sum flags and non-positive qty so that zeros from empty
    Excel cells do not distort the unit price.
    """
    if grp.empty:
        return 0.0, 0.0, None
    work = grp.copy()
    if missing_col in work.columns:
        work = work[~work[missing_col].fillna(False).astype(bool)]
    if work.empty:
        return 0.0, 0.0, None
    qty = pd.to_numeric(work[qty_col], errors="coerce").fillna(0.0)
    sm = pd.to_numeric(work[sum_col], errors="coerce").fillna(0.0)
    valid = qty > 0
    if not valid.any():
        return float(qty.sum()), float(sm.sum()), None
    qty_t = float(qty.loc[valid].sum())
    sum_t = float(sm.loc[valid].sum())
    return qty_t, sum_t, unit_price(qty_t, sum_t)


def build_store_name_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Per (exact name, store): qty/sum and unit prices (normative + actual)."""
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()
    work["name_exact"] = work["наименование"].astype(str).str.strip()
    if "книжная_норм_отсутствует" not in work.columns:
        work["книжная_норм_отсутствует"] = False
    if "книжная_факт_отсутствует" not in work.columns:
        work["книжная_факт_отсутствует"] = False

    rows: List[dict] = []
    for (name, store), grp in work.groupby(["name_exact", "магазин"], dropna=False):
        qty_n, sum_n, price_n = _agg_qty_sum_price(
            grp, "кол_учетное", "сумма_учетная", "книжная_норм_отсутствует"
        )
        qty_f, sum_f, price_f = _agg_qty_sum_price(
            grp, "кол_факт", "сумма_факт", "книжная_факт_отсутствует"
        )
        rows.append({
            "наименование": name,
            "магазин": store,
            "кол_учетное": qty_n,
            "сумма_учетная": sum_n,
            "цена_нормативная": price_n,  # сумма_учетная / кол_учетное
            "кол_факт": qty_f,
            "сумма_факт": sum_f,
            "цена_фактическая": price_f,  # сумма_факт / кол_факт
        })
    return pd.DataFrame(rows)


def compare_prices_across_stores(df: pd.DataFrame) -> pd.DataFrame:
    """Intersecting names → unit prices → pairwise store price comparison."""
    prices = build_store_name_prices(df)
    if prices.empty:
        return pd.DataFrame()

    name_counts = prices.groupby("наименование")["магазин"].nunique()
    multi = set(name_counts[name_counts >= 2].index)
    if not multi:
        return pd.DataFrame()

    rows: List[dict] = []
    for name, grp in prices[prices["наименование"].isin(multi)].groupby("наименование"):
        store_rows = list(grp.sort_values("магазин").itertuples(index=False))
        for a, b in combinations(store_rows, 2):
            price_n1 = a.цена_нормативная
            price_n2 = b.цена_нормативная
            price_f1 = a.цена_фактическая
            price_f2 = b.цена_фактическая

            gap_n = _gap_pct(price_n1, price_n2)
            gap_f = _gap_pct(price_f1, price_f2)
            st_n = _status_from_gap(gap_n)
            st_f = _status_from_gap(gap_f)
            rank = {
                STATUS_CHECK: 3,
                STATUS_NOTICE: 2,
                STATUS_MINOR: 1,
                STATUS_OK: 0,
                STATUS_NO_PRICE: -1,
            }
            status = st_n if rank.get(st_n, -1) >= rank.get(st_f, -1) else st_f
            gap_show = gap_n if gap_n is not None else gap_f
            if gap_n is not None and gap_f is not None:
                gap_show = max(gap_n, gap_f)

            comment_parts = [
                "Сравнение ЦЕН (сумма÷количество), не сумм."
            ]
            if status == STATUS_CHECK:
                comment_parts.append("Цены заметно расходятся — сверить карточки и приходы.")
            elif status == STATUS_NOTICE:
                comment_parts.append("Есть отклонение цены между магазинами.")
            elif status == STATUS_OK:
                comment_parts.append("Цены совпадают (в пределах 1%).")
            elif status == STATUS_NO_PRICE:
                comment_parts.append(
                    "Недостаточно кол-ва/суммы для расчёта цены (кол≤0 или сумма пуста)."
                )
            if price_n1 is None or price_n2 is None:
                comment_parts.append("Нормативная цена не посчитана у одного из магазинов.")
            if price_f1 is None or price_f2 is None:
                comment_parts.append("Фактическая цена не посчитана у одного из магазинов.")

            rows.append({
                "наименование": name,
                "магазин_1": a.магазин,
                "магазин_2": b.магазин,
                # Transparent inputs (sums & qty) — not used for comparison status
                "кол_норм_1": a.кол_учетное,
                "сумма_норм_1": a.сумма_учетная,
                "кол_норм_2": b.кол_учетное,
                "сумма_норм_2": b.сумма_учетная,
                "кол_факт_1": a.кол_факт,
                "сумма_факт_1": a.сумма_факт,
                "кол_факт_2": b.кол_факт,
                "сумма_факт_2": b.сумма_факт,
                # Compared values = unit prices
                "цена_книжная_нормативная_1": price_n1,
                "цена_книжная_нормативная_2": price_n2,
                "цена_книжная_фактическая_1": price_f1,
                "цена_книжная_фактическая_2": price_f2,
                "расхождение_норм": (
                    abs(price_n1 - price_n2)
                    if price_n1 is not None and price_n2 is not None
                    else None
                ),
                "расхождение_факт": (
                    abs(price_f1 - price_f2)
                    if price_f1 is not None and price_f2 is not None
                    else None
                ),
                "процент_расхождения": gap_show,
                "процент_расхождения_норм": gap_n,
                "процент_расхождения_факт": gap_f,
                "статус_проверки": status,
                "комментарий": " ".join(comment_parts),
            })

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["_rank"] = out["статус_проверки"].map(
        {STATUS_CHECK: 0, STATUS_NOTICE: 1, STATUS_MINOR: 2, STATUS_OK: 3, STATUS_NO_PRICE: 4}
    ).fillna(9)
    out = out.sort_values(
        ["_rank", "процент_расхождения"],
        ascending=[True, False],
    ).drop(columns=["_rank"])
    return out.reset_index(drop=True)


def price_compare_summary(
    price_df: pd.DataFrame,
    inventory_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """KPI for dashboard / conclusions."""
    empty = {
        "pairs": 0,
        "names": 0,
        "check": 0,
        "notice": 0,
        "ok": 0,
        "no_price": 0,
        "share_names_pct": 0.0,
        "avg_gap_pct": 0.0,
        "max_gap_pct": 0.0,
    }
    if price_df is None or price_df.empty:
        return empty
    names = int(price_df["наименование"].nunique())
    total_names = 0
    if inventory_df is not None and not inventory_df.empty:
        total_names = int(inventory_df["наименование"].astype(str).str.strip().nunique())
    st = price_df["статус_проверки"]
    gaps = price_df["процент_расхождения"].dropna()
    return {
        "pairs": int(len(price_df)),
        "names": names,
        "check": int((st == STATUS_CHECK).sum()),
        "notice": int((st == STATUS_NOTICE).sum()),
        "ok": int((st == STATUS_OK).sum()),
        "no_price": int((st == STATUS_NO_PRICE).sum()),
        "share_names_pct": (names / total_names * 100.0) if total_names else 0.0,
        "avg_gap_pct": float(gaps.mean() * 100) if len(gaps) else 0.0,
        "max_gap_pct": float(gaps.max() * 100) if len(gaps) else 0.0,
    }


def enrich_store_metrics_with_prices(
    store_metrics: pd.DataFrame,
    price_df: pd.DataFrame,
) -> pd.DataFrame:
    """Count how many price-check pairs involve each store."""
    sm = store_metrics.copy()
    if sm.empty:
        return sm
    sm["ценовых_пар"] = 0
    sm["ценовых_расхождений"] = 0
    if price_df is None or price_df.empty:
        return sm
    counts: Dict[str, int] = {}
    checks: Dict[str, int] = {}
    for _, row in price_df.iterrows():
        for key in ("магазин_1", "магазин_2"):
            s = str(row.get(key, "") or "")
            if not s:
                continue
            counts[s] = counts.get(s, 0) + 1
            if row.get("статус_проверки") in (STATUS_CHECK, STATUS_NOTICE):
                checks[s] = checks.get(s, 0) + 1
    sm["ценовых_пар"] = sm["магазин"].map(lambda x: counts.get(x, 0))
    sm["ценовых_расхождений"] = sm["магазин"].map(lambda x: checks.get(x, 0))
    return sm
