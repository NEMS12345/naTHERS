"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from planassess.model.building import BuildingModel
from planassess.samples import synthetic_house

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture()
def config_dir() -> Path:
    return CONFIG_DIR


@pytest.fixture()
def house() -> BuildingModel:
    return synthetic_house()
