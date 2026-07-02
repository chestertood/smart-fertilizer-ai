"""Crop profiles (named target ranges) and shared app state.

A profile maps each sensor name to its desired {min, max}. These reuse the
same shape as config.sensors.SENSORS so get_status() works unchanged.
"""

from config import store


# name -> {sensor -> (min, max)}
CROP_PROFILES: dict[str, dict[str, dict[str, float]]] = {
    "Leafy Greens": {
        "EC":          {"min": 1.4, "max": 2.0},
        "PH":          {"min": 5.5, "max": 6.5},
        "Temperature": {"min": 18.0, "max": 24.0},
        "Humidity":    {"min": 50.0, "max": 70.0},
    },
    "Fruiting (Tomato)": {
        "EC":          {"min": 2.0, "max": 3.5},
        "PH":          {"min": 5.8, "max": 6.3},
        "Temperature": {"min": 20.0, "max": 28.0},
        "Humidity":    {"min": 60.0, "max": 80.0},
    },
    "Herbs": {
        "EC":          {"min": 1.0, "max": 1.6},
        "PH":          {"min": 5.5, "max": 6.5},
        "Temperature": {"min": 18.0, "max": 26.0},
        "Humidity":    {"min": 50.0, "max": 70.0},
    },
}

DEFAULT_PROFILE = "Leafy Greens"


class AppState:
    """Mutable runtime state shared across views, persisted via config.store.

    Held in app.main() and passed into view builders, alongside the existing
    `updaters` dict pattern. Editable config (setpoints, auto-dose rules, pump
    calibration, sensor offsets) is loaded from disk on init and written back
    with save().
    """

    def __init__(self) -> None:
        cfg = store.load()
        # "Manual" or "Advisor" — controls how dosing decisions are made.
        self.control_mode: str = cfg.get("control_mode", "Manual")
        self.active_profile: str = cfg.get("active_profile", DEFAULT_PROFILE)
        # Editable copy of target ranges, keyed by profile name.
        self._targets: dict = cfg.get("targets", {})
        self.auto_rules: list = cfg.get("auto_rules", [])
        self.pumps: dict = cfg.get("pumps", {})
        self.offsets: dict = cfg.get("offsets", {})
        # Last sensor snapshot, kept fresh by the poll loop so any view (and
        # the LLM advisor) can read current values without its own polling.
        # Not persisted.
        self.last_readings: dict = {}

    @property
    def targets(self) -> dict[str, dict[str, float]]:
        """Editable target ranges for the active crop profile."""
        if self.active_profile not in self._targets:
            # Profile missing from saved config — seed from the defaults.
            import copy
            self._targets[self.active_profile] = copy.deepcopy(
                CROP_PROFILES.get(self.active_profile, {})
            )
        return self._targets[self.active_profile]

    def reset_targets_to_default(self) -> None:
        """Restore the active profile's setpoints to the hardcoded defaults."""
        import copy
        self._targets[self.active_profile] = copy.deepcopy(
            CROP_PROFILES.get(self.active_profile, {})
        )

    def save(self) -> None:
        """Persist editable state to disk."""
        store.save(
            {
                "active_profile": self.active_profile,
                "control_mode": self.control_mode,
                "targets": self._targets,
                "auto_rules": self.auto_rules,
                "pumps": self.pumps,
                "offsets": self.offsets,
            }
        )
