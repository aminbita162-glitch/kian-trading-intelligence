"""Operating mode configuration for Kian Trading Intelligence.

Per AD-003 and Section 01.3: a mode change must never silently enable
real-money trading. All interfaces, records, and audit events must
clearly identify the active mode.
"""

from __future__ import annotations

from contracts.enums import OperatingMode


class OperatingModeConfig:
    """Deterministic operating-mode guard.

    This is a deterministic safety guard, not an LLM-processed value.
    LIVE mode requires explicit authorization and must never be the default.
    """

    _instance: OperatingModeConfig | None = None
    _mode: OperatingMode = OperatingMode.SIMULATION
    _live_authorized: bool = False

    def __new__(cls) -> OperatingModeConfig:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def mode(self) -> OperatingMode:
        return self._mode

    @property
    def is_live(self) -> bool:
        """True only if mode is LIVE AND live_authorized is True."""
        return self._mode is OperatingMode.LIVE and self._live_authorized

    def set_mode(self, mode: OperatingMode, *, live_authorized: bool = False) -> None:
        """Set the operating mode.

        LIVE mode requires explicit live_authorized=True.
        This method does not silently enable real-money trading.
        """
        if mode is OperatingMode.LIVE and not live_authorized:
            raise PermissionError(
                "LIVE mode requires explicit live_authorized=True. "
                "Real-money trading is not enabled without authorization."
            )
        self._mode = mode
        self._live_authorized = live_authorized if mode is OperatingMode.LIVE else False

    def reset(self) -> None:
        """Reset to SIMULATION mode. For testing only."""
        self._mode = OperatingMode.SIMULATION
        self._live_authorized = False
