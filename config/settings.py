# -*- coding: utf-8 -*-
"""Настройки анализа и переносимые пути проекта.

Бизнес-пороги сохранены. Локальные абсолютные пути не зашиваются:
корневые папки вычисляются от расположения проекта и при необходимости
переопределяются через .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence, Set

# Analysis defaults (business parameters — preserved from v3.0)
PERIOD_DAYS = 30
MIN_OVERLAP_SCORE = 20
CHRONIC_MIN_STORES = 2
CHRONIC_MIN_DOCS = 3
TOP_N_NETWORK = 50
TOP_N_STORE = 10
EXCLUDE_STORE_KEYWORDS = ("итого",)
NON_RETAIL_STORES = frozenset({"РЦ", "Фабрика-кухня"})

# Scenario thresholds (rubles)
SCENARIO_LARGE_SHORTAGE = 50_000
SCENARIO_MEDIUM_SHORTAGE = 10_000
SCENARIO_WEIGHT_LOSS = 1_000

# Performance guardrails for pair matching (v4 cartesian pool — do not raise silently)
PAIR_VOLUME_LIMIT = 2_500_000
PAIR_HEAD_LIMIT = 1_200

# Candidate search before any financial overlap. Defaults stay conservative.
MATCHING_MODE = os.environ.get("MATCHING_MODE", "safe_default")
MAX_CANDIDATE_COMPARISONS = int(os.environ.get("MAX_CANDIDATE_COMPARISONS", "50000"))
MAX_ITEMS_PER_SIDE = int(os.environ.get("MAX_ITEMS_PER_SIDE", "400"))

PAIR_POOL_WARNING = (
    "Полный перебор потенциальных пар ограничен для защиты времени расчёта. "
    "При превышении порога используется приоритизированный пул кандидатов. "
    "Результат потенциальных пересортов может не включать низкоприоритетные сопоставления. "
    "Для полного расчёта необходим расширенный режим."
)


def matching_limits(
    mode: str | None = None,
    max_candidate_comparisons: int | None = None,
    max_items_per_side: int | None = None,
) -> dict:
    """Лимиты поиска кандидатов. Явные аргументы интерфейса важнее .env."""
    _load_dotenv()
    selected = (mode or os.environ.get("MATCHING_MODE") or MATCHING_MODE).strip()
    comparisons = int(max_candidate_comparisons or os.environ.get("MAX_CANDIDATE_COMPARISONS") or MAX_CANDIDATE_COMPARISONS)
    per_side = int(max_items_per_side or os.environ.get("MAX_ITEMS_PER_SIDE") or MAX_ITEMS_PER_SIDE)
    if max_candidate_comparisons is None and selected == "extended":
        comparisons = max(comparisons, 200_000)
    if max_items_per_side is None and selected == "extended":
        per_side = max(per_side, 2_000)
    if max_candidate_comparisons is None and selected == "full_manual_review":
        comparisons = max(comparisons, 1_000_000)
    if max_items_per_side is None and selected == "full_manual_review":
        per_side = max(per_side, 5_000)
    return {
        "mode": selected,
        "max_candidate_comparisons": comparisons,
        "max_items_per_side": per_side,
    }

# Overlap export limit
OVERLAP_EXPORT_ROWS = 500


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


_load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parent


class PathConfigError(Exception):
    """Понятная ошибка пути: какой файл/папка ожидались и что сделать."""


def _resolve_dir(raw: Optional[str], default: Path) -> Path:
    """Разрешить путь из .env. Относительные пути считаются от корня проекта."""
    if raw is None:
        return default
    value = raw.strip().strip('"').strip("'")
    if not value or value in (".",):
        return default
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
    return path


def _env_dir(*names: str, default: Path) -> Path:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return _resolve_dir(raw, default)
    return default


INPUT_DIR = _env_dir("INVENTORY_DATA_DIR", "INPUT_DIR", default=WORKSPACE_ROOT)
OUTPUT_DIR = _env_dir("INVENTORY_OUTPUT_DIR", "OUTPUT_DIR", default=WORKSPACE_ROOT)
TEMPLATES_DIR = _env_dir("TEMPLATES_DIR", default=WORKSPACE_ROOT)
REFERENCE_DIR = _env_dir("REFERENCE_DIR", default=PROJECT_ROOT / "data")
LOGS_DIR = _env_dir("LOGS_DIR", default=PROJECT_ROOT / "logs")
TEMP_DIR = _env_dir("TEMP_DIR", default=PROJECT_ROOT / "temp")
DATA_DIR = REFERENCE_DIR


def ensure_runtime_dirs() -> None:
    """Создать служебные папки, если их ещё нет."""
    for directory in (OUTPUT_DIR, LOGS_DIR, TEMP_DIR, REFERENCE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def require_dir(path: Path, purpose: str) -> Path:
    if path.is_dir():
        return path
    raise PathConfigError(
        f"{purpose} не найдена.\n"
        f"Ожидалась папка: {path}\n"
        f"Создайте её или укажите другой путь в файле .env "
        f"(INVENTORY_DATA_DIR / INVENTORY_OUTPUT_DIR)."
    )


def require_file(path: Path, purpose: str, hint: str = "") -> Path:
    if path.is_file():
        return path
    extra = f"\n{hint}" if hint else ""
    raise PathConfigError(
        f"{purpose} не найден.\n"
        f"Ожидался файл: {path}\n"
        f"Положите файл в эту папку или выберите другой через диалог.{extra}"
    )


def format_missing_file(path: Path, purpose: str) -> str:
    return (
        f"{purpose} не найден.\n"
        f"Ожидался файл: {path}\n"
        f"Проверьте имя файла и папку поиска: {path.parent}"
    )


@dataclass
class Settings:
    """Application settings loaded from environment / defaults."""

    period_days: int = PERIOD_DAYS
    min_overlap_score: int = MIN_OVERLAP_SCORE
    chronic_min_stores: int = CHRONIC_MIN_STORES
    chronic_min_docs: int = CHRONIC_MIN_DOCS
    top_n_network: int = TOP_N_NETWORK
    top_n_store: int = TOP_N_STORE
    enable_cross_store: bool = False
    default_search_dir: Optional[str] = None
    catalog_filename: str = "nomenclature.csv"
    exclude_store_keywords: Sequence[str] = field(
        default_factory=lambda: EXCLUDE_STORE_KEYWORDS
    )
    non_retail_stores: Set[str] = field(
        default_factory=lambda: set(NON_RETAIL_STORES)
    )

    @property
    def search_dir(self) -> Path:
        if self.default_search_dir:
            return _resolve_dir(self.default_search_dir, INPUT_DIR)
        return INPUT_DIR

    @property
    def output_dir(self) -> Path:
        return OUTPUT_DIR


def load_settings() -> Settings:
    """Загрузить настройки из окружения и создать служебные папки."""
    _load_dotenv()
    ensure_runtime_dirs()
    return Settings(
        period_days=int(os.environ.get("PERIOD_DAYS", PERIOD_DAYS)),
        min_overlap_score=int(os.environ.get("MIN_OVERLAP_SCORE", MIN_OVERLAP_SCORE)),
        enable_cross_store=os.environ.get("ENABLE_CROSS_STORE", "0").strip()
        in ("1", "true", "True", "yes", "YES"),
        default_search_dir=os.environ.get("INVENTORY_DATA_DIR") or None,
    )
