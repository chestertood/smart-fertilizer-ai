import flet as ft

# min/max = the sensor's own physical measurement range (hardware datasheet
# spec), not a curated agricultural "healthy" band — the widest range that
# makes sense, per the user's request. This is the fallback used when no crop
# target is set, and the seed for brand-new custom profiles; tighten to an
# actual crop-appropriate band via a crop profile / the Parameters page.
# Sources: Atlas Scientific EZO-EC / EZO-pH circuit datasheets; DHT22 datasheet.
SENSORS = [
    {
        "name": "EC",
        "value": 2.1,
        "unit": "mS/cm",
        "min": 0.0,
        "max": 500.0,   # Atlas EZO-EC circuit: 0.07–500,000 µS/cm
        "abs_max": 500.0,
        "icon": ft.Icons.ELECTRIC_BOLT,
        "color": "#2196F3",
    },
    {
        "name": "PH",
        "value": 6,
        "unit": "pH",
        "min": 0.0,
        "max": 14.0,    # Atlas EZO-pH circuit: 0.001–14.000 pH
        "abs_max": 14.0,
        "icon": ft.Icons.SCIENCE,
        "color": "#9C27B0",
    },
    {
        "name": "Temperature",
        "value": 24.5,
        "unit": "°C",
        "min": -40.0,
        "max": 80.0,    # DHT22: -40 to 80°C
        "abs_max": 80.0,
        "icon": ft.Icons.THERMOSTAT,
        "color": "#FF9800",
    },
    {
        "name": "Humidity",
        "value": 65.0,
        "unit": "%",
        "min": 0.0,
        "max": 100.0,   # DHT22: 0–100% RH
        "abs_max": 100.0,
        "icon": ft.Icons.WATER_DROP,
        "color": "#009688",
    },
]


def get_status(value: float, min_val: float, max_val: float) -> tuple[str, str]:
    if value < min_val:
        return "Too Low", "#F44336"
    if value > max_val:
        return "Too High", "#F44336"
    margin = (max_val - min_val) * 0.15
    if value < min_val + margin or value > max_val - margin:
        return "Warning", "#FF9800"
    return "Normal", "#4CAF50"
