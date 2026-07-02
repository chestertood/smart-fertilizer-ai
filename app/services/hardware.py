import sys
import time
import random
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

_IS_PI = sys.platform.startswith("linux")


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
# Atlas Scientific EZO sensors (I2C)
# Command protocol: write ASCII cmd → wait → read response bytes
# Byte 0 = status code (1 = success), bytes 1‥N = ASCII value string
# ---------------------------------------------------------------------------

class _AtlasEZO(Sensor):
    """Base for Atlas Scientific EZO-* I2C sensors."""

    # Minimum milliseconds the sensor needs after a 'R' command
    _READ_DELAY_MS: int = 900

    def __init__(self, name: str, i2c_address: int, simulated_base: float):
        super().__init__(name)
        self._address = i2c_address
        self._sim_base = simulated_base
        self._bus = None
        self._sim: SimulatedSensor | None = None

    def connect(self) -> bool:
        if not _IS_PI:
            self._sim = SimulatedSensor(self.name, self._sim_base)
            return self._sim.connect()
        try:
            import smbus2  # type: ignore
            self._bus = smbus2.SMBus(1)
            self._connected = True
            logger.info("%s: I2C bus opened (addr=0x%02X)", self.name, self._address)
            return True
        except Exception as exc:
            logger.error("%s: connect failed — %s", self.name, exc)
            return False

    def read(self) -> float:
        if self._sim:
            return self._sim.read()
        try:
            # Send 'R' (read) command
            self._bus.write_i2c_block_data(self._address, 0x00, [ord("R")])
            time.sleep(self._READ_DELAY_MS / 1000)
            # Read 7 bytes; first byte is status
            data = self._bus.read_i2c_block_data(self._address, 0x00, 7)
            if data[0] != 1:
                raise IOError(f"EZO status byte={data[0]}")
            raw = bytes(data[1:]).split(b"\x00")[0].decode("ascii").strip()
            return round(float(raw), 2)
        except Exception as exc:
            logger.error("%s: read failed — %s", self.name, exc)
            raise

    def disconnect(self) -> None:
        if self._bus:
            self._bus.close()
            self._bus = None
        if self._sim:
            self._sim.disconnect()
        super().disconnect()


class ECSensor(_AtlasEZO):
    """Atlas Scientific EZO-EC (default I2C address 0x64)."""

    DEFAULT_ADDRESS = 0x64

    def __init__(self, i2c_address: int = DEFAULT_ADDRESS):
        super().__init__("EC", i2c_address, simulated_base=2.1)
        self._READ_DELAY_MS = 600


class PHSensor(_AtlasEZO):
    """Atlas Scientific EZO-pH (default I2C address 0x63)."""

    DEFAULT_ADDRESS = 0x63

    def __init__(self, i2c_address: int = DEFAULT_ADDRESS):
        super().__init__("PH", i2c_address, simulated_base=6.2)
        self._READ_DELAY_MS = 900


# ---------------------------------------------------------------------------
# DHT22 — temperature + humidity on a single GPIO pin
# ---------------------------------------------------------------------------

class _DHT22Base(Sensor):
    """Shared GPIO setup for both readings off the same DHT22 chip."""

    _gpio_pin: int = 4  # BCM pin; override per instance

    def __init__(self, name: str, gpio_pin: int, simulated_base: float):
        super().__init__(name)
        self._gpio_pin = gpio_pin
        self._sim_base = simulated_base
        self._device = None
        self._sim: SimulatedSensor | None = None

    def connect(self) -> bool:
        if not _IS_PI:
            self._sim = SimulatedSensor(self.name, self._sim_base)
            return self._sim.connect()
        try:
            import board  # type: ignore
            import adafruit_dht  # type: ignore
            pin = getattr(board, f"D{self._gpio_pin}")
            self._device = adafruit_dht.DHT22(pin)
            self._connected = True
            logger.info("%s: DHT22 ready (GPIO%d)", self.name, self._gpio_pin)
            return True
        except Exception as exc:
            logger.error("%s: connect failed — %s", self.name, exc)
            return False

    def _raw_read(self) -> tuple[float, float]:
        """Returns (temperature_c, humidity_pct)."""
        return self._device.temperature, self._device.humidity

    def disconnect(self) -> None:
        if self._device:
            try:
                self._device.exit()
            except Exception:
                pass
            self._device = None
        if self._sim:
            self._sim.disconnect()
        super().disconnect()


class TemperatureSensor(_DHT22Base):
    """DHT22 temperature reading in °C."""

    def __init__(self, gpio_pin: int = 4):
        super().__init__("Temperature", gpio_pin, simulated_base=24.5)

    def read(self) -> float:
        if self._sim:
            return self._sim.read()
        temp, _ = self._raw_read()
        return round(temp, 1)


class HumiditySensor(_DHT22Base):
    """DHT22 relative humidity reading in %."""

    def __init__(self, gpio_pin: int = 4):
        super().__init__("Humidity", gpio_pin, simulated_base=65.0)

    def read(self) -> float:
        if self._sim:
            return self._sim.read()
        _, hum = self._raw_read()
        return round(hum, 1)


# ---------------------------------------------------------------------------
# SensorHub — owns all sensor instances and exposes a single read interface
# ---------------------------------------------------------------------------

class SensorHub:
    """Manages all sensors; call read_all() to get the current snapshot."""

    def __init__(
        self,
        ec_address: int = ECSensor.DEFAULT_ADDRESS,
        ph_address: int = PHSensor.DEFAULT_ADDRESS,
        dht_gpio_pin: int = 4,
    ):
        self._sensors: dict[str, Sensor] = {
            "EC":          ECSensor(ec_address),
            "PH":          PHSensor(ph_address),
            "Temperature": TemperatureSensor(dht_gpio_pin),
            "Humidity":    HumiditySensor(dht_gpio_pin),
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
