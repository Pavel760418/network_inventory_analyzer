# -*- coding: utf-8 -*-
"""Рейтинг магазинов. Формула v4 сохранена. Считается только по операционному контуру.

store_score =
  percentile(shrinkage, лучше меньше) * 0.35
  + percentile(recovery, лучше больше) * 0.25
  + percentile(чистые недостачи, лучше меньше) * 0.25
  + percentile(SKU с расхождениями, лучше меньше) * 0.15

Более высокий балл — лучше. Место 1 — лучший балл.
Хозтовары, тара и упаковка в этот расчёт не входят.
Суммы излишков, аномалий и резерва показаны с весом 0: в формуле v4 их нет.
"""
from __future__ import annotations

import pandas as pd

from src.metrics import calc_store_metrics, percentile_rank
from src.network_inventory_analyzer.scope_classifier import production_mask
from src.network_inventory_analyzer.settings import RATING_WEIGHTS


def rate_stores(df: pd.DataFrame, overlap: pd.DataFrame) -> pd.DataFrame:
    scoped = df[production_mask(df, "include_in_store_rating")].copy()
    if scoped.empty:
        return pd.DataFrame()
    metrics = calc_store_metrics(scoped, overlap if overlap is not None else pd.DataFrame())
    if metrics.empty:
        return metrics
    metrics = metrics.sort_values(["store_score", "магазин"], ascending=[False, True]).reset_index(drop=True)
    metrics["место"] = range(1, len(metrics) + 1)
    metrics["балл_потерь"] = (metrics["score_shrink"] * RATING_WEIGHTS["shrinkage_pct"]).round(4)
    metrics["балл_восстановления"] = (metrics["score_recovery"] * RATING_WEIGHTS["recovery_pct"]).round(4)
    metrics["балл_недостач"] = (metrics["score_net"] * RATING_WEIGHTS["чистые_недостачи"]).round(4)
    metrics["балл_sku"] = (
        percentile_rank(metrics["sku_с_расх"], invert=True) * RATING_WEIGHTS["sku_с_расх"]
    ).round(4)
    metrics["балл_излишков"] = 0.0
    metrics["балл_пересортов"] = metrics["балл_восстановления"]
    metrics["балл_аномалий"] = 0.0
    metrics["балл_резерва"] = 0.0
    metrics["штрафы_бонусы"] = 0.0
    metrics["сумма_компонент"] = (
        metrics["балл_потерь"]
        + metrics["балл_недостач"]
        + metrics["балл_пересортов"]
        + metrics["балл_sku"]
        + metrics["балл_излишков"]
        + metrics["балл_аномалий"]
        + metrics["балл_резерва"]
        + metrics["штрафы_бонусы"]
    ).round(4)
    metrics["объяснение"] = metrics.apply(_explain, axis=1)
    return metrics


def _explain(row: pd.Series) -> str:
    return (
        f"Место {int(row['место'])}, балл {row['store_score']}. "
        f"Чистые недостачи {row['чистые_недостачи']:.2f} ₽ дают компонент {row['балл_недостач']:.2f}. "
        f"Доля потерь {row['shrinkage_pct']:.2f}% даёт {row['балл_потерь']:.2f}. "
        f"Восстановление перекрытием {row['recovery_pct']:.1f}% даёт {row['балл_пересортов']:.2f}. "
        f"Хозтовары в балл не входят. Излишки, аномалии и резерв показаны с весом 0."
    )


def rating_components(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics is None or metrics.empty:
        return pd.DataFrame()
    cols = [
        "магазин", "балл_недостач", "балл_излишков", "балл_пересортов",
        "балл_аномалий", "балл_резерва", "балл_потерь", "балл_sku",
        "штрафы_бонусы", "сумма_компонент", "store_score", "место", "объяснение",
        "чистые_недостачи", "излишки", "недостачи", "перекрытие",
    ]
    have = [c for c in cols if c in metrics.columns]
    return metrics[have].copy()


def why_store(metrics: pd.DataFrame, lines: pd.DataFrame, store: str) -> pd.DataFrame:
    row = metrics[metrics["магазин"] == store]
    if row.empty:
        return pd.DataFrame()
    info = row.iloc[0]
    factors = pd.DataFrame(
        [
            {"фактор": "Чистые недостачи, ₽", "значение": info["чистые_недостачи"], "компонент_балла": info["балл_недостач"]},
            {"фактор": "Shrinkage, %", "значение": info["shrinkage_pct"], "компонент_балла": info["балл_потерь"]},
            {"фактор": "Восстановление перекрытием, %", "значение": info["recovery_pct"], "компонент_балла": info["балл_пересортов"]},
            {"фактор": "SKU с расхождениями", "значение": info["sku_с_расх"], "компонент_балла": info["балл_sku"]},
            {"фактор": "Излишки (вес 0)", "значение": info["излишки"], "компонент_балла": 0},
        ]
    )
    sku = lines[(lines["магазин"] == store) & (lines["недостача_сумма"] > 0)].sort_values(
        "недостача_сумма", ascending=False
    ).head(10)
    sku = sku[["наименование", "category_group", "недостача_сумма"]].copy() if not sku.empty else sku
    factors.attrs["sku"] = sku
    factors.attrs["explanation"] = info["объяснение"]
    return factors
