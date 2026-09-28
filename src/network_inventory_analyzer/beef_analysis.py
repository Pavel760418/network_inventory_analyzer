# -*- coding: utf-8 -*-
"""Контур говядины. Подтверждённые строки — только active=1 в beef_scope.csv.

Совпадение по имени без строки справочника даёт статус
«предварительно классифицировано» и не входит в подтверждённые суммы.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src.network_inventory_analyzer.normalizer import norm_txt
from src.network_inventory_analyzer.settings import BEEF_SCOPE


def load_beef_scope(path: Optional[Path] = None) -> pd.DataFrame:
    file = path or BEEF_SCOPE
    if not file.is_file():
        return pd.DataFrame()
    return pd.read_csv(file, dtype=str).fillna("")


def mark_beef(df: pd.DataFrame, scope: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    out = df.copy()
    scope = scope if scope is not None else load_beef_scope()
    by_name = {}
    by_sku = {}
    if scope is not None and not scope.empty:
        for _, row in scope.iterrows():
            if str(row.get("name", "")).strip():
                by_name[norm_txt(row["name"])] = row
            if str(row.get("sku", "")).strip():
                by_sku[str(row["sku"]).strip()] = row

    statuses = []
    groups = []
    cuts = []
    confirmed = []
    for _, line in out.iterrows():
        art = str(line.get("артикул", "") or "").strip()
        name = norm_txt(line.get("наименование", ""))
        hit = by_sku.get(art) if art else None
        if hit is None:
            hit = by_name.get(name)
        if hit is not None:
            active = str(hit.get("active", "0")).strip().lower() in ("1", "true", "yes", "да")
            statuses.append("подтверждено" if active else "на проверке")
            groups.append(hit.get("beef_group", ""))
            cuts.append(hit.get("cut", ""))
            confirmed.append(active)
            continue
        if "говяд" in name:
            statuses.append("предварительно классифицировано")
            groups.append("кандидат по наименованию")
            cuts.append("")
            confirmed.append(False)
            continue
        statuses.append("")
        groups.append("")
        cuts.append("")
        confirmed.append(False)
    out["beef_status"] = statuses
    out["beef_group"] = groups
    out["beef_cut"] = cuts
    out["beef_confirmed"] = confirmed
    out["beef_related"] = out["beef_status"] != ""
    return out


def beef_views(df: pd.DataFrame, regrades: pd.DataFrame, prices: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    related = df[df["beef_related"]].copy() if "beef_related" in df.columns else df.iloc[0:0]
    confirmed = df[df["beef_confirmed"]].copy() if "beef_confirmed" in df.columns else df.iloc[0:0]
    names = set(confirmed["наименование"].astype(str)) if not confirmed.empty else set()

    def _filter_pairs(frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty or not names:
            return pd.DataFrame(columns=getattr(frame, "columns", []))
        mask = frame["излишек_sku"].astype(str).isin(names) | frame["недостача_sku"].astype(str).isin(names)
        return frame[mask].copy()

    price = pd.DataFrame()
    if prices is not None and not prices.empty and names:
        name_cols = [c for c in ("наименование", "name") if c in prices.columns]
        if name_cols:
            price = prices[prices[name_cols[0]].astype(str).isin(names)].copy()
    return {
        "summary": _summary(confirmed, related),
        "shortages": confirmed[confirmed["недостача_сумма"] > 0].copy() if not confirmed.empty else confirmed,
        "surpluses": confirmed[confirmed["излишек_сумма"] > 0].copy() if not confirmed.empty else confirmed,
        "pairs": _filter_pairs(regrades),
        "related": related,
        "prices": price,
        "full": related,
    }


def _summary(confirmed: pd.DataFrame, related: pd.DataFrame) -> pd.DataFrame:
    if confirmed is None:
        confirmed = pd.DataFrame()
    shortage = float(confirmed["недостача_сумма"].sum()) if not confirmed.empty else 0.0
    surplus = float(confirmed["излишек_сумма"].sum()) if not confirmed.empty else 0.0
    return pd.DataFrame(
        [
            {"показатель": "Подтверждённые недостачи, ₽", "значение": round(shortage, 2)},
            {"показатель": "Подтверждённые излишки, ₽", "значение": round(surplus, 2)},
            {"показатель": "SKU подтверждено", "значение": int(confirmed["наименование"].nunique()) if not confirmed.empty else 0},
            {"показатель": "Магазинов", "значение": int(confirmed["магазин"].nunique()) if not confirmed.empty else 0},
            {
                "показатель": "Строк на проверке или предварительно",
                "значение": int((~related["beef_confirmed"]).sum()) if not related.empty and "beef_confirmed" in related.columns else 0,
            },
        ]
    )
