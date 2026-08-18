"""SenseCAP RS485 temperature/humidity decoding.

Run with:  python -m unittest discover tests -v
Stdlib unittest only — no hardware, no extra dependencies.
"""

import unittest

from app.services.hardware import CO2Sensor, HumiditySensor, TemperatureSensor


class _FakeInstrument:
    """Records the query and returns a canned 32-bit raw value."""

    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def read_long(self, register, functioncode=3, signed=False):
        self.calls.append((register, functioncode, signed))
        return self.raw


def _wire(sensor, raw):
    """Force the Pi read path on any platform."""
    sensor._sim = None
    sensor._instrument = _FakeInstrument(raw)
    return sensor._instrument


class SenseCAPDecodeTest(unittest.TestCase):

    def test_temperature_scaled_and_signed(self):
        s = TemperatureSensor()
        inst = _wire(s, 23456)
        self.assertEqual(s.read(), 23.46)
        self.assertEqual(inst.calls, [(0x0000, 3, True)])

    def test_temperature_below_zero(self):
        s = TemperatureSensor()
        _wire(s, -4500)
        self.assertEqual(s.read(), -4.5)

    def test_humidity_scaled_from_second_register_pair(self):
        s = HumiditySensor()
        inst = _wire(s, 65100)
        self.assertEqual(s.read(), 65.1)
        self.assertEqual(inst.calls, [(0x0002, 3, False)])

    def test_co2_scaled_from_third_register_pair(self):
        s = CO2Sensor()
        inst = _wire(s, 812000)
        self.assertEqual(s.read(), 812.0)
        self.assertEqual(inst.calls, [(0x0004, 3, False)])

    def test_no_de_re_toggling_on_usb_adapter(self):
        s = TemperatureSensor()
        _wire(s, 1000)
        self.assertIsNone(s._de_re)
        self.assertEqual(s.read(), 1.0)  # would raise if it toggled a None pin

    def test_simulated_read_without_hardware(self):
        s = HumiditySensor()
        self.assertTrue(s.connect() or s._instrument is not None)
        self.assertIsInstance(s.read(), float)


if __name__ == "__main__":
    unittest.main()
