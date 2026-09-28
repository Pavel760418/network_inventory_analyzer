# -*- coding: utf-8 -*-
"""Release 4 tests: book-sum anomalies + cross-store price comparison."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.anomalies import (
    TYPE_1,
    TYPE_2,
    TYPE_3,
    anomalies_summary,
    detect_book_sum_anomalies,
    enrich_store_metrics_with_anomalies,
)
from src.metrics import generate_conclusions
from src.price_compare import (
    STATUS_CHECK,
    STATUS_OK,
    compare_prices_across_stores,
    price_compare_summary,
)


def _base_row(**kwargs):
    row = {
        "магазин": "Автодом",
        "документ": "D1",
        "наименование": "Товар X",
        "кол_учетное": 0.0,
        "кол_факт": 1.0,
        "сумма_учетная": 0.0,
        "сумма_факт": 100.0,
        "излишек_сумма": 100.0,
        "недостача_сумма": 0.0,
        "книжная_норм_отсутствует": False,
        "книжная_факт_отсутствует": False,
    }
    row.update(kwargs)
    return row


def test_anomaly_type2_both_missing():
    df = pd.DataFrame([
        _base_row(
            наименование="Пустой обеих",
            книжная_норм_отсутствует=True,
            книжная_факт_отсутствует=True,
            сумма_факт=0.0,
            излишек_сумма=0.0,
        ),
    ])
    out = detect_book_sum_anomalies(df)
    assert len(out) == 1
    assert out.iloc[0]["тип_аномалии"] == TYPE_2
    assert out.iloc[0]["критичность"] == "ДА"


def test_anomaly_type1_unique_store():
    df = pd.DataFrame([
        _base_row(
            наименование="Уникальный крахмал",
            магазин="Автодом",
            книжная_норм_отсутствует=True,
            книжная_факт_отсутствует=False,
            сумма_факт=236.4,
            излишек_сумма=236.4,
        ),
    ])
    out = detect_book_sum_anomalies(df)
    assert len(out) == 1
    assert out.iloc[0]["тип_аномалии"] == TYPE_1
    assert out.iloc[0]["критичность"] == "НЕТ"


def test_anomaly_type3_cross_store_review():
    df = pd.DataFrame([
        _base_row(
            наименование="Крахмал произ",
            магазин="Автодом",
            книжная_норм_отсутствует=True,
            книжная_факт_отсутствует=False,
            сумма_факт=236.4,
            излишек_сумма=236.4,
        ),
        _base_row(
            наименование="Крахмал произ",
            магазин="БКК",
            книжная_норм_отсутствует=False,
            книжная_факт_отсутствует=False,
            кол_учетное=1.0,
            сумма_учетная=50.0,
            сумма_факт=50.0,
            излишек_сумма=0.0,
        ),
    ])
    out = detect_book_sum_anomalies(df)
    assert len(out) == 1
    assert out.iloc[0]["тип_аномалии"] == TYPE_3
    assert "БКК" in str(out.iloc[0]["другие_магазины"])


def test_anomalies_summary_and_store_enrich():
    df = pd.DataFrame([
        _base_row(наименование="A", книжная_норм_отсутствует=True, книжная_факт_отсутствует=True),
        _base_row(наименование="B", книжная_норм_отсутствует=True, книжная_факт_отсутствует=False),
    ])
    anom = detect_book_sum_anomalies(df)
    smry = anomalies_summary(anom, total_rows=10)
    assert smry["total"] == 2
    assert smry["critical"] == 1
    assert smry["share_pct"] == 20.0

    stores = pd.DataFrame({
        "магазин": ["Автодом"],
        "класс": ["A"],
        "store_score": [90],
        "излишки": [1],
        "недостачи": [1],
        "сальдо": [0],
        "перекрытие": [0],
        "чистые_недостачи": [1],
        "shrinkage_pct": [1],
        "recovery_pct": [0],
        "документов": [1],
        "место": [1],
    })
    enriched = enrich_store_metrics_with_anomalies(stores, anom)
    assert int(enriched.iloc[0]["аномалий"]) == 2
    assert int(enriched.iloc[0]["аномалий_критич"]) == 1


def test_price_compare_exact_name_no_mix():
    df = pd.DataFrame([
        {
            "магазин": "Маг1", "наименование": "Соус соевый 30г",
            "кол_учетное": 10, "кол_факт": 10,
            "сумма_учетная": 100, "сумма_факт": 100,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
        {
            "магазин": "Маг2", "наименование": "Соус соевый 30г",
            "кол_учетное": 10, "кол_факт": 10,
            "сумма_учетная": 200, "сумма_факт": 200,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
        {
            "магазин": "Маг1", "наименование": "Другой товар",
            "кол_учетное": 1, "кол_факт": 1,
            "сумма_учетная": 10, "сумма_факт": 10,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
    ])
    out = compare_prices_across_stores(df)
    assert len(out) == 1
    assert out.iloc[0]["наименование"] == "Соус соевый 30г"
    # Prices = sum/qty → 100/10=10 vs 200/10=20 — NOT raw sums 100 vs 200
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_1"]) - 10.0) < 1e-9
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_2"]) - 20.0) < 1e-9
    assert abs(float(out.iloc[0]["сумма_норм_1"]) - 100.0) < 1e-9  # sum kept for transparency
    assert out.iloc[0]["статус_проверки"] == STATUS_CHECK
    assert abs(float(out.iloc[0]["процент_расхождения"]) - 0.5) < 1e-9

    smry = price_compare_summary(out, df)
    assert smry["pairs"] == 1
    assert smry["names"] == 1
    assert smry["check"] == 1


def test_unit_price_is_sum_div_qty_not_sum():
    """Regression: comparison must use price=sum/qty, never raw book sums."""
    from src.price_compare import unit_price, build_store_name_prices

    assert abs(unit_price(2.0, 100.0) - 50.0) < 1e-9
    assert unit_price(0.0, 100.0) is None

    df = pd.DataFrame([
        {
            "магазин": "A", "наименование": "Товар",
            "кол_учетное": 0.5, "кол_факт": 1.0,
            "сумма_учетная": 200.0, "сумма_факт": 400.0,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
        {
            "магазин": "B", "наименование": "Товар",
            "кол_учетное": 2.0, "кол_факт": 2.0,
            "сумма_учетная": 200.0, "сумма_факт": 400.0,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
    ])
    prices = build_store_name_prices(df)
    a = prices[prices["магазин"] == "A"].iloc[0]
    b = prices[prices["магазин"] == "B"].iloc[0]
    # Same sum 200, different qty → different unit prices 400 vs 100
    assert abs(float(a["цена_нормативная"]) - 400.0) < 1e-6
    assert abs(float(b["цена_нормативная"]) - 100.0) < 1e-6
    assert float(a["сумма_учетная"]) == float(b["сумма_учетная"]) == 200.0

    out = compare_prices_across_stores(df)
    assert len(out) == 1
    # Must NOT treat equal sums as equal prices
    assert out.iloc[0]["статус_проверки"] == STATUS_CHECK
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_1"]) - 400.0) < 1e-6
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_2"]) - 100.0) < 1e-6


def test_price_compare_matching_prices_ok():
    df = pd.DataFrame([
        {
            "магазин": "A", "наименование": "Молоко",
            "кол_учетное": 2, "кол_факт": 2,
            "сумма_учетная": 100, "сумма_факт": 100,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
        {
            "магазин": "B", "наименование": "Молоко",
            "кол_учетное": 4, "кол_факт": 4,
            "сумма_учетная": 200, "сумма_факт": 200,
            "книжная_норм_отсутствует": False, "книжная_факт_отсутствует": False,
        },
    ])
    out = compare_prices_across_stores(df)
    assert len(out) == 1
    # 100/2 = 50, 200/4 = 50 → same unit price
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_1"]) - 50.0) < 1e-9
    assert abs(float(out.iloc[0]["цена_книжная_нормативная_2"]) - 50.0) < 1e-9
    assert out.iloc[0]["статус_проверки"] == STATUS_OK


def test_conclusions_include_anomalies_and_prices():
    lines = generate_conclusions(
        {
            "stores": 1, "docs": 1, "sku_disc": 1,
            "surplus": 1, "shortage": 1, "net": 0,
            "overlap": 0, "recovery_pct": 0, "clean_shortage": 1,
            "non_homogeneous_surplus": 0, "shrinkage_pct": 0,
        },
        pd.DataFrame({"магазин": ["A"]}),
        pd.DataFrame(),
        anom_summary={
            "total": 5, "critical": 2, "type1": 1, "type2": 2, "type3": 2, "share_pct": 3.5,
        },
        price_summary={
            "names": 10, "pairs": 20, "check": 3, "notice": 2,
            "share_names_pct": 12.0, "avg_gap_pct": 8.5,
        },
    )
    titles = [t for t, _ in lines]
    assert "Аномалии книжных сумм" in titles
    assert "Цены между магазинами" in titles
