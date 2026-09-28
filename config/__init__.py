"""Пакет конфигурации проекта."""
from .settings import (
    INPUT_DIR,
    OUTPUT_DIR,
    PROJECT_ROOT,
    REFERENCE_DIR,
    WORKSPACE_ROOT,
    PathConfigError,
    Settings,
    ensure_runtime_dirs,
    load_settings,
)

__all__ = [
    "INPUT_DIR",
    "OUTPUT_DIR",
    "PROJECT_ROOT",
    "REFERENCE_DIR",
    "WORKSPACE_ROOT",
    "PathConfigError",
    "Settings",
    "ensure_runtime_dirs",
    "load_settings",
]
