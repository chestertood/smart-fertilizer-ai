# EC + pH Sensor Wiring (RS485 Modbus RTU via MAX485)

Two sensors, two MAX485 boards, one shared UART bus.

```
                         RASPBERRY PI 5 (40-pin header)
                        ┌───────────────────────────┐
                        │  1  3V3          5V  2    │
                        │  3  GPIO2       5V  4     │
                        │  5  GPIO3      GND  6 ─────┼───┐  common GND
                        │  7  GPIO4     GPIO14 8 ────┼───┼───► TXD (shared)
                        │  9  GND      GPIO15 10 ────┼───┼───◄ RXD (shared)
                        │ 11  GPIO17   GPIO18 12      │   │
                        │       (Nutrient A pump)     │   │
                        │ ...                         │   │
                        │ 29  GPIO5 ──────────────────┼───┼───► DE/RE (EC module)
                        │ 31  GPIO6 ──────────────────┼───┼───► DE/RE (pH module)
                        └───────────────────────────┘   │
                                                          │
        ┌─────────────────────────┐    ┌─────────────────────────┐
        │   MAX485 MODULE #1      │    │   MAX485 MODULE #2      │
        │   (EC / TDS sensor)     │    │   (pH sensor)           │
        │                         │    │                         │
        │  DI  ◄── GPIO14 (TXD)   │    │  DI  ◄── GPIO14 (TXD)   │
        │  RO  ──► GPIO15 (RXD)   │    │  RO  ──► GPIO15 (RXD)   │
        │  DE+RE ◄── GPIO5        │    │  DE+RE ◄── GPIO6        │
        │  VCC ◄── 3.3V *see note │    │  VCC ◄── 3.3V *see note │
        │  GND ──── common GND ───┼────┼──────────────────────── │
        │                         │    │                         │
        │  A ──► EC sensor A (+)  │    │  A ──► pH sensor A (+)  │
        │  B ──► EC sensor B (-)  │    │  B ──► pH sensor B (-)  │
        └─────────────────────────┘    └─────────────────────────┘

        ┌─────────────────────────┐    ┌─────────────────────────┐
        │  EC/TDS SENSOR          │    │  pH SENSOR (BPHT-RS485) │
        │  044,000 uS/cm          │    │  0-14pH                 │
        │  Modbus slave ID: 1     │    │  Modbus slave ID: 2     │
        │  Power: 12-24V DC ──────┼──┐ │  Power: 12-24V DC ──────┼──┐
        │  GND ───────────────────┼──┼─┼──────────────────────── │  │
        └─────────────────────────┘  │ └─────────────────────────┘  │
                                      │                              │
                                      ▼                              ▼
                              12-24V DC PSU (shared, NOT from Pi 5V rail)
                              PSU GND tied to Pi GND (common ground)
```

## Pin summary

| Signal          | Pi 5 pin      | Goes to                          |
|------------------|--------------|-----------------------------------|
| GPIO14 (TXD)     | pin 8        | DI on both MAX485 (shared bus)    |
| GPIO15 (RXD)     | pin 10       | RO on both MAX485 (shared bus)    |
| GPIO5            | pin 29       | DE+RE on MAX485 #1 (EC)           |
| GPIO6            | pin 31       | DE+RE on MAX485 #2 (pH)           |
| 3.3V             | pin 1        | VCC on both MAX485 *(see note)*   |
| GND              | pin 6/9/14…  | GND on both MAX485 + PSU ground   |

Already-used GPIOs on this project (do not reuse): 17, 27, 22, 23, 24 — dosing pumps (`app/services/actuators.py`).

## Notes

- **Voltage**: generic MAX485 breakouts are 5V-logic parts; DI/DE/RE inputs are not always 3.3V-safe. Check your module's datasheet — if 5V logic, add a level shifter or use a 3.3V-logic MAX485 variant. Frying a Pi GPIO here is the main risk.
- **Sensor power**: EC and pH probes need 12-24V DC — a separate PSU, not the Pi's 5V rail. Tie PSU ground to Pi ground (common reference) even though power is separate.
- **Slave IDs**: both sensors sit on the same A/B bus (shared TXD/RXD), so they *must* have different Modbus slave addresses — factory default is often `1` for both; change one via the vendor's config tool/DIP switch before wiring together.
- Matches `app/services/hardware.py` (`ECSensor`, `PHSensor`, `_ModbusRTUSensor`) — GPIO5/6 and slave IDs 1/2 are the code's defaults.
