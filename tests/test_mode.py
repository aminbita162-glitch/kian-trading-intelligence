"""Tests for operating mode guard (AD-003, Section 01.3).

Verifies that a mode change never silently enables real-money trading.
"""

import pytest

from contracts.enums import OperatingMode
from contracts.mode import OperatingModeConfig


@pytest.fixture()
def mode_config() -> OperatingModeConfig:
    """Fresh mode config for each test."""
    config = OperatingModeConfig()
    config.reset()
    return config


class TestOperatingMode:
    def test_default_mode_is_simulation(self, mode_config: OperatingModeConfig) -> None:
        assert mode_config.mode is OperatingMode.SIMULATION
        assert mode_config.is_live is False

    def test_paper_mode_is_not_live(self, mode_config: OperatingModeConfig) -> None:
        mode_config.set_mode(OperatingMode.PAPER)
        assert mode_config.mode is OperatingMode.PAPER
        assert mode_config.is_live is False

    def test_live_mode_requires_authorization(self, mode_config: OperatingModeConfig) -> None:
        with pytest.raises(PermissionError, match="LIVE mode requires explicit"):
            mode_config.set_mode(OperatingMode.LIVE)

    def test_live_mode_with_authorization(self, mode_config: OperatingModeConfig) -> None:
        mode_config.set_mode(OperatingMode.LIVE, live_authorized=True)
        assert mode_config.mode is OperatingMode.LIVE
        assert mode_config.is_live is True

    def test_live_without_authorization_flag_is_not_live(
        self, mode_config: OperatingModeConfig
    ) -> None:
        mode_config.set_mode(OperatingMode.LIVE, live_authorized=False)
        assert mode_config.mode is OperatingMode.LIVE
        assert mode_config.is_live is False

    def test_reset_returns_to_simulation(self, mode_config: OperatingModeConfig) -> None:
        mode_config.set_mode(OperatingMode.PAPER)
        mode_config.reset()
        assert mode_config.mode is OperatingMode.SIMULATION
        assert mode_config.is_live is False
