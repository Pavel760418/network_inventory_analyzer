# -*- coding: utf-8 -*-
from pathlib import Path

import pytest

from scripts.build_demo_inventory import build
from src.network_inventory_analyzer.pipeline import analyze

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def bundle():
    path = build(ROOT / "sample_data" / "demo_inventory_synthetic.xlsx")
    return analyze(path, period_days=30)
