from __future__ import annotations

from datetime import date

import pytest

from fulfillment.generator.simulate import SimulationConfig, SimulationResult, simulate

SMALL = SimulationConfig(start=date(2024, 1, 1), end=date(2024, 3, 31), orders_per_day=40, seed=7)


@pytest.fixture(scope="session")
def small_sim() -> SimulationResult:
    return simulate(SMALL)


@pytest.fixture(scope="session")
def full_sim() -> SimulationResult:
    """Default-size simulation (~190k orders) - used for KPI calibration checks."""
    return simulate(SimulationConfig())
