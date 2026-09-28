# -*- coding: utf-8 -*-
"""Сборка контура v2 поверх действующих расчётов v4."""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.capitalization import match_capitalization_to_inventory, parse_capitalization_excel
from src.overlap import build_operational_overlaps
from src.network_inventory_analyzer.beef_analysis import beef_views, mark_beef
from src.network_inventory_analyzer.category_reserve import category_reserve
from src.network_inventory_analyzer.coverage import build_completeness
from src.network_inventory_analyzer.dashboard_metrics import conclusions, kpis
from src.network_inventory_analyzer.data_loader import load_inventory
from src.network_inventory_analyzer.posted_surpluses import analyze_posted
from src.network_inventory_analyzer.price_anomalies import price_anomalies
from src.network_inventory_analyzer.regrading import (
    applied_regrades,
    build_dictionary_regrades,
    candidate_regrades,
)
from src.network_inventory_analyzer.related_pairs import load_pairs, pair_issues
from src.network_inventory_analyzer.scope_classifier import (
    classify_lines,
    household_frame,
    unclassified_frame,
)
from src.network_inventory_analyzer.shortages import shortage_lines, surplus_lines
from src.network_inventory_analyzer.store_rating import rate_stores, rating_components
from src.network_inventory_analyzer.validators import allocation_ok


def analyze(
    inventory_path: str | Path,
    period_days: int = 30,
    end_date: Optional[datetime.date] = None,
    capitalization_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    lines, meta, notes = load_inventory(inventory_path, period_days, end_date)
    lines = classify_lines(lines)
    lines = mark_beef(lines)

    rating_scope = lines[lines["include_in_store_rating"] == True].copy()  # noqa: E712
    legacy = build_operational_overlaps(rating_scope) if not rating_scope.empty else pd.DataFrame()
    pairs = load_pairs()
    regrades = build_dictionary_regrades(lines, pairs, legacy)
    applied = applied_regrades(regrades)
    candidates = candidate_regrades(regrades)
    reserve = category_reserve(lines, legacy, applied)
    rating = rate_stores(lines, legacy)
    components = rating_components(rating)
    prices = price_anomalies(lines)
    beef = beef_views(lines, regrades, prices)

    cap = pd.DataFrame()
    if capitalization_path:
        cap = match_capitalization_to_inventory(parse_capitalization_excel(str(capitalization_path)), lines)
    posted = analyze_posted(cap, lines, regrades)

    shortages = shortage_lines(lines, operational_only=False)
    surpluses = surplus_lines(lines, operational_only=False)
    household = household_frame(lines)
    unclassified = unclassified_frame(lines)

    quality = list(notes)
    quality.extend(pair_issues(pairs))
    quality.extend(allocation_ok(applied, lines))
    if not quality:
        quality.append("Проверки справочника и распределения прошли без замечаний.")

    bundle: Dict[str, Any] = {
        "meta": meta,
        "lines": lines,
        "legacy_overlap": legacy,
        "regrades": regrades,
        "applied_pairs": applied,
        "candidates": candidates,
        "reserve": reserve,
        "rating": rating,
        "rating_components": components,
        "prices": prices,
        "beef_summary": beef["summary"],
        "beef_shortages": beef["shortages"],
        "beef_surpluses": beef["surpluses"],
        "beef_pairs": beef["pairs"],
        "beef_prices": beef["prices"],
        "beef_full": beef["full"],
        "posted_summary": posted["summary"],
        "posted_linked": posted["linked"],
        "posted_candidates": posted["candidates"],
        "posted_unlinked": posted["unlinked"],
        "posted_hypotheses": posted["hypotheses"],
        "posted_full": posted["full"],
        "shortages": shortages,
        "surpluses": surpluses,
        "household": household,
        "unclassified": unclassified,
        "quality": quality,
        "period_days": period_days,
    }
    bundle["kpi"] = kpis(bundle)
    bundle["conclusions"] = conclusions(bundle)
    bundle["completeness"] = _completeness(bundle)
    return bundle


def _completeness(bundle: Dict[str, Any]) -> pd.DataFrame:
    same = [
        ("Недостачи", bundle["shortages"]),
        ("Излишки", bundle["surpluses"]),
        ("Пересорты", bundle["regrades"]),
        ("Перекрытия v4", bundle["legacy_overlap"]),
        ("Кандидаты на пересорт", bundle["candidates"]),
        ("Оприходованные излишки", bundle["posted_full"]),
        ("Аномалии цен", bundle["prices"]),
        ("Говядина", bundle["beef_full"]),
        ("Хозтовары и упаковка", bundle["household"]),
        ("Без классификации", bundle["unclassified"]),
        ("Резерв категорий", bundle["reserve"]),
    ]
    return build_completeness((name, frame, frame, "") for name, frame in same)
