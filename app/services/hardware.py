import os
import sys
import time
import random
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# Real hardware on Linux, simulated everywhere else. SENSOR_SIM=1 forces
# simulation on the Pi too, for UI work before the probes are wired up —
# without it every read fails and the dashboard shows NaN.
_IS_PI = sys.platform.startswith("linux") and os.environ.get("SENSOR_SIM") != "1"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Sensor(ABC):
    """Abstract base for every physical or simulated sensor."""

    def __init__(self, name: str):
        self.name = name
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Open the hardware connection. Returns True on success."""

    @abstractmethod
    def read(self) -> float:
        """Return the latest measurement as a float."""

    def disconnect(self) -> None:
        self._connected = False
        logger.info("%s: disconnected", self.name)

    @property
    def is_connected(self) -> bool:
        return self._connected


# ---------------------------------------------------------------------------
# Simulation (Windows dev / unit tests)
# ---------------------------------------------------------------------------

class SimulatedSensor(Sensor):
    """Stable mock value with small Gaussian noise — no hardware required."""

    def __init__(self, name: str, base_value: float, noise_pct: float = 0.02):
        super().__init__(name)
        self._base = base_value
        self._noise_pct = noise_pct

    def connect(self) -> bool:
        self._connected = True
        logger.info("SimulatedSensor[%s]: ready (base=%.2f)", self.name, self._base)
        return True

    def read(self) -> float:
        spread = self._base * self._noise_pct
        return round(self._base + random.uniform(-spread, spread), 2)


# ---------------------------------------------------------------------------
# RS485 Modbus RTU sensors
#   * EC/TDS + pH probes sit on the Pi UART (GPIO14 TXD / GPIO15 RXD) behind
#     MAX485 modules; each gets its own DE/RE GPIO toggled HIGH only while a
#     query is in flight.
#   * SenseCAP CO2/Temp/Humidity sits on a USB-RS485 dongle (/dev/ttyUSB0),
#     which switches direction in hardware — de_re_pin=None, no GPIO.
# Register address/scale defaults are common-convention guesses — confirm
# against your sensor's Modbus register map before trusting readings.
# ---------------------------------------------------------------------------

class _ModbusRTUSensor(Sensor):
    """Base for a Modbus RTU holding-register sensor."""

    _REGISTER: int = 0
    _SCALE: float = 100.0  # raw register value / SCALE = measurement
    _LONG: bool = False    # True = value spans two registers (32-bit)
    _SIGNED: bool = False  # 32-bit reads only; True lets values go negative

    def __init__(self, name: str, slave_id: int, de_re_pin: int | None,
                 port: str, simulated_base: float, baudrate: int = 9600):
        super().__init__(name)
        self._slave_id = slave_id
        self._de_re_pin = de_re_pin
        self._port = port
        self._baudrate = baudrate
        self._sim_base = simulated_base
        self._instrument = None
        self._de_re = None
        self._sim: SimulatedSensor | None = None

    def connect(self) -> bool:
        if not _IS_PI:
            self._sim = SimulatedSensor(self.name, self._sim_base)
            return self._sim.connect()
        try:
            import minimalmodbus  # type: ignore
            if self._de_re_pin is not None:
                from gpiozero import DigitalOutputDevice  # type: ignore
                self._de_re = DigitalOutputDevice(self._de_re_pin, initial_value=False)
            # minimalmodbus caches one pyserial object per port name, so two
            # sensors on the same dongle share it instead of fighting over it.
            self._instrument = minimalmodbus.Instrument(self._port, self._slave_id)
            self._instrument.serial.baudrate = self._baudrate
            self._instrument.serial.timeout = 0.3
            self._connected = True
            logger.info("%s: Modbus RTU ready (%s, slave=%d, DE/RE=%s)",
                        self.name, self._port, self._slave_id,
                        f"GPIO{self._de_re_pin}" if self._de_re_pin is not None else "auto")
            return True
        except Exception as exc:
            logger.error("%s: connect failed — %s", self.name, exc)
            return False

    def read(self) -> float:
        if self._sim:
            return self._sim.read()
        try:
            # ponytail: DE/RE held high for the whole query (write+response)
            # instead of dropping it right after the write. Simplest thing
            # that works at slow poll rates; if reads start corrupting,
            # switch to Pi hardware RTS-based RS485 mode for tight timing.
            if self._de_re:
                self._de_re.on()
            if self._LONG:
                raw = self._instrument.read_long(
                    self._REGISTER, functioncode=3, signed=self._SIGNED)
            else:
                raw = self._instrument.read_register(self._REGISTER, functioncode=3)
        finally:
            if self._de_re:
                self._de_re.off()
        return round(raw / self._SCALE, 2)

    def disconnect(self) -> None:
        if self._de_re:
            self._de_re.close()
            self._de_re = None
        self._instrument = None
        if self._sim:
            self._sim.disconnect()
        super().disconnect()


class ECSensor(_ModbusRTUSensor):
    """EC/TDS RS485 Modbus RTU probe (0-44,000 uS/cm)."""

    DEFAULT_SLAVE_ID = 1

    def __init__(self, slave_id: int = DEFAULT_SLAVE_ID, de_re_pin: int = 5,
                 port: str = "/dev/ttyAMA0"):
        super().__init__("EC", slave_id, de_re_pin, port, simulated_base=2.1)
        self._SCALE = 1.0  # raw register = uS/cm directly — verify vs datasheet


class PHSensor(_ModbusRTUSensor):
    """BPHT-RS485 pH probe (0-14pH, RS485 Modbus RTU)."""

    DEFAULT_SLAVE_ID = 2

    def __init__(self, slave_id: int = DEFAULT_SLAVE_ID, de_re_pin: int = 6,
                 port: str = "/dev/ttyAMA0"):
        super().__init__("PH", slave_id, de_re_pin, port, simulated_base=6.2)
        self._SCALE = 100.0  # raw register = pH * 100 — verify vs datasheet


# ---------------------------------------------------------------------------
# SenseCAP S-CO2-02B — CO2 + temperature + humidity, RS485 Modbus RTU
# Wired through a USB-RS485 adapter (A->A, B->B, 5-16V power, GND common).
# Factory defaults: slave address 1, 9600 8N1.
# Each measurement occupies TWO holding registers (32-bit, value = raw / 1000):
#   0x0000 temperature °C (signed)   0x0002 humidity %RH   0x0004 CO2 ppm
# Verify against the register map in the SenseCAP user manual before trusting
# readings — if the sensor was re-addressed, pass the new slave_id.
# ---------------------------------------------------------------------------

SENSECAP_PORT = "/dev/ttyUSB0"   # USB-RS485 dongle; COM3-style on Windows
SENSECAP_SLAVE_ID = 1


class TemperatureSensor(_ModbusRTUSensor):
    """SenseCAP temperature reading in °C."""

    _REGISTER = 0x0000
    _SCALE = 1000.0
    _LONG = True
    _SIGNED = True  # below-freezing readings come back negative

    def __init__(self, slave_id: int = SENSECAP_SLAVE_ID,
                 port: str = SENSECAP_PORT):
        super().__init__("Temperature", slave_id, None, port, simulated_base=24.5)


class HumiditySensor(_ModbusRTUSensor):
    """SenseCAP relative humidity reading in %RH."""

    _REGISTER = 0x0002
    _SCALE = 1000.0
    _LONG = True

    def __init__(self, slave_id: int = SENSECAP_SLAVE_ID,
                 port: str = SENSECAP_PORT):
        super().__init__("Humidity", slave_id, None, port, simulated_base=65.0)


class CO2Sensor(_ModbusRTUSensor):
    """SenseCAP CO2 reading in ppm (0-10,000)."""

    _REGISTER = 0x0004
    _SCALE = 1000.0
    _LONG = True

    def __init__(self, slave_id: int = SENSECAP_SLAVE_ID,
                 port: str = SENSECAP_PORT):
        super().__init__("CO2", slave_id, None, port, simulated_base=800.0)


# ---------------------------------------------------------------------------
# SensorHub — owns all sensor instances and exposes a single read interface
# ---------------------------------------------------------------------------

class SensorHub:
    """Manages all sensors; call read_all() to get the current snapshot."""

    def __init__(
        self,
        ec_slave_id: int = ECSensor.DEFAULT_SLAVE_ID,
        ph_slave_id: int = PHSensor.DEFAULT_SLAVE_ID,
        sensecap_slave_id: int = SENSECAP_SLAVE_ID,
        sensecap_port: str = SENSECAP_PORT,
    ):
        self._sensors: dict[str, Sensor] = {
            "EC":          ECSensor(ec_slave_id),
            "PH":          PHSensor(ph_slave_id),
            "Temperature": TemperatureSensor(sensecap_slave_id, sensecap_port),
            "Humidity":    HumiditySensor(sensecap_slave_id, sensecap_port),
            # Read and logged, but not on the dashboard: adding it to
            # config.sensors.SENSORS needs a matching target range in every
            # saved profile, plus a co2 column in readings. database.log_reading
            # ignores unknown keys, so this is harmless until then.
            "CO2":         CO2Sensor(sensecap_slave_id, sensecap_port),
        }

    def connect_all(self) -> dict[str, bool]:
        """Connect every sensor. Returns {name: success} map."""
        return {name: s.connect() for name, s in self._sensors.items()}

    def disconnect_all(self) -> None:
        for s in self._sensors.values():
            s.disconnect()

    def read(self, name: str) -> float:
        """Read a single sensor by name."""
        return self._sensors[name].read()

    def read_all(self) -> dict[str, float]:
        """Return {name: value} for every sensor."""
        results: dict[str, float] = {}
        for name, sensor in self._sensors.items():
            try:
                results[name] = sensor.read()
            except Exception as exc:
                logger.error("read_all: %s failed — %s", name, exc)
                results[name] = float("nan")
        return results

    @property
    def sensors(self) -> dict[str, Sensor]:
        return self._sensors
