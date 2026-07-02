import sys
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

_IS_PI = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Actuator(ABC):
    """Abstract base for every physical or simulated dosing device.

    Shape mirrors app.services.hardware.Sensor so a real GPIO-driven pump can
    drop in behind this interface later with no changes to the UI or control
    logic.
    """

    def __init__(self, name: str, max_dose: float):
        self.name = name
        # Hard per-pump ceiling. Every dose() call clamps to this — the single
        # safety choke point for both manual and LLM-approved dosing.
        self.max_dose = max_dose
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Open the hardware connection. Returns True on success."""

    @abstractmethod
    def _run(self, amount: float) -> None:
        """Actually drive the device for the (already-clamped) amount."""

    def dose(self, amount: float) -> float:
        """Dispense `amount` (ml), clamped to [0, max_dose]. Returns the
        amount actually dispensed."""
        if not self._connected:
            raise RuntimeError(f"{self.name}: not connected")
        clamped = max(0.0, min(float(amount), self.max_dose))
        if clamped != amount:
            logger.warning(
                "%s: dose %.2f clamped to %.2f (max=%.2f)",
                self.name, amount, clamped, self.max_dose,
            )
        self._run(clamped)
        return clamped

    def disconnect(self) -> None:
        self._connected = False
        logger.info("%s: disconnected", self.name)

    @property
    def is_connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Simulation (Windows dev / no hardware)
# ---------------------------------------------------------------------------

class SimulatedPump(Actuator):
    """Pretends to dispense — just logs the action. No hardware required."""

    def connect(self) -> bool:
        self._connected = True
        logger.info("SimulatedPump[%s]: ready (max=%.2f ml)", self.name, self.max_dose)
        return True

    def _run(self, amount: float) -> None:
        logger.info("SimulatedPump[%s]: dispensed %.2f ml", self.name, amount)


# ---------------------------------------------------------------------------
# Relay-driven peristaltic pump (Raspberry Pi GPIO) — real hardware path.
# Calibrate ml_per_second per pump; dose() converts ml -> on-time.
# ---------------------------------------------------------------------------

class RelayPump(Actuator):
    """GPIO relay pump. Only used on the Pi; imports gpiozero lazily."""

    def __init__(self, name: str, max_dose: float, gpio_pin: int,
                 ml_per_second: float = 1.0):
        super().__init__(name, max_dose)
        self._gpio_pin = gpio_pin
        self._ml_per_second = ml_per_second
        self._relay = None

    def connect(self) -> bool:
        try:
            from gpiozero import OutputDevice  # type: ignore
            # active_high=False suits common low-level-trigger relay boards.
            self._relay = OutputDevice(
                self._gpio_pin, active_high=False, initial_value=False
            )
            self._connected = True
            logger.info("%s: relay ready (GPIO%d)", self.name, self._gpio_pin)
            return True
        except Exception as exc:
            logger.error("%s: connect failed — %s", self.name, exc)
            return False

    def _run(self, amount: float) -> None:
        import time
        seconds = amount / self._ml_per_second if self._ml_per_second else 0.0
        self._relay.on()
        time.sleep(seconds)
        self._relay.off()

    def disconnect(self) -> None:
        if self._relay:
            try:
                self._relay.off()
                self._relay.close()
            except Exception:
                pass
            self._relay = None
        super().disconnect()


# ---------------------------------------------------------------------------
# ActuatorHub — owns all pumps; parallel to SensorHub
# ---------------------------------------------------------------------------

# (name, max_dose_ml, gpio_pin) — gpio_pin only used on the Pi.
_PUMP_CONFIG = [
    ("Nutrient A", 50.0, 17),
    ("Nutrient B", 50.0, 27),
    ("pH Up",      20.0, 22),
    ("pH Down",    20.0, 23),
    ("Water",     200.0, 24),
]


class ActuatorHub:
    """Manages all pumps; call dose(name, amount) to dispense."""

    def __init__(self):
        self._pumps: dict[str, Actuator] = {}
        for name, max_dose, pin in _PUMP_CONFIG:
            if _IS_PI:
                self._pumps[name] = RelayPump(name, max_dose, pin)
            else:
                self._pumps[name] = SimulatedPump(name, max_dose)

    def connect_all(self) -> dict[str, bool]:
        """Connect every pump. Returns {name: success} map."""
        return {name: p.connect() for name, p in self._pumps.items()}

    def disconnect_all(self) -> None:
        for p in self._pumps.values():
            p.disconnect()

    def dose(self, name: str, amount: float) -> float:
        """Dispense `amount` ml from the named pump (clamped). Returns the
        amount actually dispensed."""
        if name not in self._pumps:
            raise KeyError(f"Unknown pump: {name}")
        return self._pumps[name].dose(amount)

    def apply_config(self, state) -> None:
        """Push calibration (max_dose, ml_per_s) from AppState onto the live
        pump objects so edits on the Parameters page take effect immediately."""
        for name, cfg in getattr(state, "pumps", {}).items():
            pump = self._pumps.get(name)
            if pump is None:
                continue
            if "max_dose" in cfg:
                pump.max_dose = float(cfg["max_dose"])
            # ml_per_s only matters for real RelayPumps.
            if "ml_per_s" in cfg and hasattr(pump, "_ml_per_second"):
                pump._ml_per_second = float(cfg["ml_per_s"])

    @property
    def pumps(self) -> dict[str, Actuator]:
        return self._pumps
