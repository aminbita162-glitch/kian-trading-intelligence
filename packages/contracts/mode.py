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

    def set_mode(self, mode: OperatingMode, *, live_authorized: bool | None = None) -> None:
        """Set the operating mode.

        LIVE mode requires an explicit authorization decision:
        - ``live_authorized=True`` enables live trading (``is_live`` is True).
        - ``live_authorized=False`` sets LIVE mode but trading stays disabled.
        - ``live_authorized`` omitted (None) raises PermissionError — the
          caller must make an explicit decision before entering LIVE mode.

        This method does not silently enable real-money trading.
        """
        if mode is OperatingMode.LIVE and live_authorized is None:
            raise PermissionError(
                "LIVE mode requires explicit live_authorized (True or False). "
                "Real-money trading is not enabled without explicit authorization."
            )
        self._mode = mode
        self._live_authorized = live_authorized is True if mode is OperatingMode.LIVE else False

    def reset(self) -> None:
        """Reset to SIMULATION mode. For testing only."""
        self._mode = OperatingMode.SIMULATION
        self._live_authorized = False
