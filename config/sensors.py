import flet as ft

SENSORS = [
    {
        "name": "EC",
        "value": 2.1,
        "unit": "mS/cm",
        "min": 1.5,
        "max": 3.0,
        "abs_max": 5.0,
        "icon": ft.Icons.ELECTRIC_BOLT,
        "color": "#2196F3",
    },
    {
        "name": "PH",
        "value": 6,
        "unit": "pH",
        "min": 5.5,
        "max": 7.0,
        "abs_max": 14.0,
        "icon": ft.Icons.SCIENCE,
        "color": "#9C27B0",
    },
    {
        "name": "Temperature",
        "value": 24.5,
        "unit": "°C",
        "min": 18.0,
        "max": 28.0,
        "abs_max": 50.0,
        "icon": ft.Icons.THERMOSTAT,
        "color": "#FF9800",
    },
    {
        "name": "Humidity",
        "value": 65.0,
        "unit": "%",
        "min": 50.0,
        "max": 80.0,
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
