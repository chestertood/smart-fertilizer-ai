# 🌱 Smart Fertilizer — AI-Assisted Hydroponic Control

A desktop/touchscreen control app for hydroponic fertigation, built with [Flet](https://flet.dev) and powered by Claude for AI-assisted dosing decisions. Designed to run on a Raspberry Pi with real sensors and dosing pumps, and to fall back to full simulation on any dev machine — no hardware required to build or demo.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Flet](https://img.shields.io/badge/flet-0.85.1-informational)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20%7C%20Windows%20%7C%20Linux-lightgrey)

## Overview

The app monitors EC, pH, temperature, and humidity in real time, and helps decide how to dose nutrients and pH adjusters — either **manually** by the operator, or via **Claude-recommended actions that require human approval** before anything runs. Every dose (manual or AI-suggested) is clamped to safe limits and logged, and the whole thing is navigable from a single touchscreen-friendly side rail.

### Why "advisor + approve," not autonomous?

Fertigation mistakes are hard to undo — over-dosing can damage or kill a crop. The LLM here is a **recommendation engine, not an actuator**. It reasons over live readings and target ranges and proposes actions with a rationale; a human always presses "Approve" before a pump moves.

## Features

- **Live Dashboard** — real-time EC / pH / Temperature / Humidity cards with status coloring (Normal / Warning / Too High-Low) and online/offline connectivity indicator.
- **Parameters page** — one screen to manually configure:
  - **Setpoints** per crop profile (target min/max per sensor), with a live status dot as you edit.
  - **Auto-dose rules** (e.g. "if EC < 1.8 → dose Nutrient A 10ml") — stored and editable now; the automatic execution engine is a planned follow-up.
  - **Manual dosing** — trigger any pump on demand with a safety-clamped amount.
  - **Calibration** — per-pump max dose / throughput, per-sensor offsets.
  - A sticky **unsaved-changes bar** (Save / Reset) keeps edits explicit before they're persisted.
- **LLM Advisor** — sends current readings + active crop profile to Claude via structured tool-use, gets back concrete dosing actions with reasoning, and dispenses only on manual approval.
- **History** — logged sensor trends and a full dosing event log (manual vs. LLM-sourced).
- **Settings** — control mode (Manual / Advisor), crop profile selection, API key status.

## Architecture

```
main.py                     # Entry point — desktop window or web view
app/
  app.py                    # Wires views, nav rail, sensor/actuator polling loops
  components/
    app_bar.py               # Top bar with control-mode indicator
    nav_rail.py               # Side navigation (Dashboard/Parameters/Advisor/History/Settings)
    sensor_card.py             # Reusable live sensor readout card
  views/
    dashboard.py              # Live sensor grid
    parameters.py              # Manual setpoints / rules / dosing / calibration
    advisor.py                 # LLM-driven recommend → approve → dose flow
    history.py                 # Trends + dosing log
    settings_view.py           # Mode / profile / API key status
  services/
    hardware.py               # Sensor abstraction: simulated + Atlas Scientific EZO (I2C) + DHT22
    actuators.py               # Pump abstraction: simulated + GPIO relay-driven dosing
    database.py                # SQLite logging (readings + dosing_events)
    llm_agent.py                # Claude tool-use integration for dosing recommendations
config/
  sensors.py                 # Sensor metadata + status thresholds
  profiles.py                 # Crop profiles, shared AppState
  store.py                   # JSON persistence for user-editable config
```

### Simulation-first hardware design

Every physical I/O path (`Sensor`, `Actuator`) has a real implementation *and* a `Simulated*` counterpart. The app auto-detects the platform (`sys.platform.startswith("linux")`) and falls back to realistic simulated values when hardware libraries aren't available — so the full UI and control flow can be developed and demoed on any machine, then dropped onto a Pi with zero code changes.

Supported real hardware:
- **Atlas Scientific EZO-EC / EZO-pH** over I2C
- **DHT22** temperature + humidity sensor
- **GPIO relay-driven** peristaltic dosing pumps

## Getting Started

```bash
git clone https://github.com/chestertood/smart-fertilizer-ai.git
cd smart-fertilizer-ai
pip install -r requirements.txt
```

Create a `.env` file with your Anthropic API key (only needed for the LLM Advisor):

```
ANTHROPIC_API_KEY=your-key-here
```

Run it:

```bash
python main.py
```

Runs as a native desktop window by default. To run as a web view instead:

```bash
FLET_VIEW=web python main.py
```

### On a Raspberry Pi

Uncomment the hardware section in `requirements.txt` (`smbus2`, `adafruit-circuitpython-dht`, `adafruit-blinka`, `gpiozero`) and install. The app will automatically use real sensors/pumps instead of simulation.

## Tech Stack

- **UI:** [Flet](https://flet.dev) (Flutter-backed Python UI framework)
- **AI:** [Anthropic Claude](https://www.anthropic.com) via structured tool-use
- **Storage:** SQLite (sensor history + dosing events), JSON (user config)
- **Hardware:** I2C (Atlas Scientific EZO), GPIO (relays), DHT22

## Roadmap

- [ ] Auto-dose rule execution engine (rules are configurable today; not yet enforced automatically)
- [ ] ML-based trend prediction / anomaly detection on logged sensor history
- [ ] Sensor calibration offsets applied at read-time
- [ ] Dose rate-limiting / cooldown safety window

## License

MIT
