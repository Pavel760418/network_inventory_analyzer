# -*- coding: utf-8 -*-
"""Полный список ценовых пар. Обрезка Top-N здесь не применяется."""
from __future__ import annotations

import pandas as pd

from src.price_compare import compare_prices_across_stores


def price_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return compare_prices_across_stores(df)
