# -*- coding: utf-8 -*-
"""Полные списки недостач и излишков без Top-N."""
from __future__ import annotations

import pandas as pd

from src.network_inventory_analyzer.scope_classifier import production_mask


def shortage_lines(df: pd.DataFrame, operational_only: bool = False) -> pd.DataFrame:
    work = df[production_mask(df, "include_in_shortage_top")] if operational_only else df
    out = work[work["недостача_сумма"] > 0].copy()
    return out.sort_values("недостача_сумма", ascending=False)


def surplus_lines(df: pd.DataFrame, operational_only: bool = False) -> pd.DataFrame:
    work = df[production_mask(df, "include_in_production_score")] if operational_only else df
    out = work[work["излишек_сумма"] > 0].copy()
    return out.sort_values("излишек_сумма", ascending=False)
