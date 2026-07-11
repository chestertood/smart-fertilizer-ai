"""Crop profiles (named target ranges) and shared app state.

A profile maps each sensor name to its desired {min, max}. These reuse the
same shape as config.sensors.SENSORS so get_status() works unchanged.
"""

from datetime import date

from config import store

# Single shared default target range — every profile uses this same band.
# No per-crop split: one set of setpoints for all profiles.
import copy as _copy

DEFAULT_TARGETS: dict[str, dict[str, float]] = {
    "EC":          {"min": 0.5, "max": 4.0},
    "PH":          {"min": 5.0, "max": 7.5},
    "Temperature": {"min": 10.0, "max": 35.0},
    "Humidity":    {"min": 30.0, "max": 90.0},
}

# Generic starting ranges for a brand-new custom profile.
_GENERIC_DEFAULTS = _copy.deepcopy(DEFAULT_TARGETS)


# name -> {sensor -> (min, max)}. All profiles seeded from the same defaults.
CROP_PROFILES: dict[str, dict[str, dict[str, float]]] = {
    "Leafy Greens":      _copy.deepcopy(DEFAULT_TARGETS),
    "Fruiting (Tomato)": _copy.deepcopy(DEFAULT_TARGETS),
    "Herbs":             _copy.deepcopy(DEFAULT_TARGETS),
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
        self.active_profile: str = cfg.get("active_profile", DEFAULT_PROFILE)
        # Editable copy of target ranges, keyed by profile name.
        self._targets: dict = cfg.get("targets", {})
        self.auto_rules: list = cfg.get("auto_rules", [])
        self.pumps: dict = cfg.get("pumps", {})
        self.offsets: dict = cfg.get("offsets", {})
        # Built-in profile names the operator deleted (see delete_profile).
        self.hidden_profiles: set = set(cfg.get("hidden_profiles", []))
        # Reservoir dimensions (cm) for capacity / dosing math.
        self.water_tank: dict = cfg.get(
            "water_tank", {"width_cm": 30.0, "length_cm": 30.0, "height_cm": 40.0}
        )
        # Growth-stage tracking, keyed by profile name — see growth_config().
        self.growth: dict = cfg.get("growth", {})
        # UI language: "en" or "th" (see config.i18n.t()).
        self.language: str = cfg.get("language", "en")
        # Claude model for the chat assistant (see llm_agent.AVAILABLE_MODELS).
        self.llm_model: str = cfg.get("llm_model", "claude-opus-4-8")
        # Last sensor snapshot, kept fresh by the poll loop so any view (and
        # the LLM advisor) can read current values without its own polling.
        # Not persisted.
        self.last_readings: dict = {}

    @property
    def profile_names(self) -> list[str]:
        """All selectable profile names: the built-in ones first (minus any
        the operator deleted), then any custom profiles created (via Settings
        or the chat assistant's set_parameters proposal), in creation order."""
        names = [n for n in CROP_PROFILES if n not in self.hidden_profiles]
        for name in self._targets:
            if name not in names and name not in self.hidden_profiles:
                names.append(name)
        return names

    def create_profile(self, name: str) -> bool:
        """Create a new custom crop profile seeded with generic defaults and
        make it active. Returns False if the name is blank or already taken."""
        import copy
        name = (name or "").strip()
        if not name or name in self.profile_names:
            return False
        self._targets[name] = copy.deepcopy(_GENERIC_DEFAULTS)
        self.active_profile = name
        return True

    def delete_profile(self, name: str) -> bool:
        """Delete a profile (built-in or custom). Refuses to delete the last
        remaining profile. Switches active_profile to another one if the
        deleted profile was active. Returns False if not allowed."""
        names = self.profile_names
        if name not in names or len(names) <= 1:
            return False
        self._targets.pop(name, None)
        if name in CROP_PROFILES:
            self.hidden_profiles.add(name)
        if self.active_profile == name:
            remaining = [n for n in names if n != name]
            self.active_profile = remaining[0]
        return True

    @property
    def targets(self) -> dict[str, dict[str, float]]:
        """Editable target ranges for the active crop profile — the current
        growth stage's ranges if a grow cycle is being tracked (see
        current_stage_info), else the profile's flat range."""
        info = self.current_stage_info()
        if info is not None:
            return info["stage"]["targets"]
        if self.active_profile not in self._targets:
            # Profile missing from saved config — seed from the defaults.
            import copy
            self._targets[self.active_profile] = copy.deepcopy(
                CROP_PROFILES.get(self.active_profile, {})
            )
        return self._targets[self.active_profile]

    # -- growth-stage tracking (per profile) ---------------------------------

    def growth_config(self, profile: str | None = None) -> dict:
        """{"planting_date", "stages"} for a profile (active profile if not
        given), creating an empty tracking entry on first access."""
        name = profile or self.active_profile
        if name not in self.growth:
            self.growth[name] = {"planting_date": None, "stages": []}
        return self.growth[name]

    def add_stage(self, name: str, duration_days: int) -> None:
        """Append a new growth stage to the active profile, seeded with that
        profile's current flat target ranges (edit them individually after)."""
        import copy
        g = self.growth_config()
        base = (
            self._targets.get(self.active_profile)
            or CROP_PROFILES.get(self.active_profile)
            or _GENERIC_DEFAULTS
        )
        g["stages"].append({
            "name": (name or "Stage").strip() or "Stage",
            "duration_days": max(1, int(duration_days)),
            "targets": copy.deepcopy(base),
        })

    def delete_stage(self, index: int) -> bool:
        g = self.growth_config()
        if 0 <= index < len(g["stages"]):
            g["stages"].pop(index)
            return True
        return False

    def start_planting(self, date_str: str | None = None) -> None:
        """Begin (or restart) growth tracking for the active profile from
        today, or a given ISO date (YYYY-MM-DD)."""
        g = self.growth_config()
        g["planting_date"] = date_str or date.today().isoformat()

    def stop_planting(self) -> None:
        """Stop tracking — targets fall back to the flat profile range."""
        g = self.growth_config()
        g["planting_date"] = None

    def current_stage_info(self) -> dict | None:
        """Progress through the active profile's growth cycle, or None if
        that profile isn't tracking one (no planting date or no stages).

        Returns {"stage_index", "stage", "day_in_stage", "elapsed_days",
        "total_days", "overall_pct"}. Clamps to the last stage once the
        total duration has elapsed (doesn't fall off the end)."""
        g = self.growth_config()
        stages = g.get("stages") or []
        planting = g.get("planting_date")
        if not stages or not planting:
            return None
        try:
            start = date.fromisoformat(planting)
        except ValueError:
            return None

        elapsed_days = max(0, (date.today() - start).days)
        total_days = sum(s["duration_days"] for s in stages)
        cum = 0
        for i, s in enumerate(stages):
            cum_prev = cum
            cum += s["duration_days"]
            if elapsed_days < cum:
                return {
                    "stage_index": i,
                    "stage": s,
                    "day_in_stage": elapsed_days - cum_prev + 1,
                    "elapsed_days": elapsed_days,
                    "total_days": total_days,
                    "overall_pct": round(min(100.0, elapsed_days / total_days * 100), 1)
                    if total_days else 0.0,
                }
        last = stages[-1]
        return {
            "stage_index": len(stages) - 1,
            "stage": last,
            "day_in_stage": last["duration_days"],
            "elapsed_days": elapsed_days,
            "total_days": total_days,
            "overall_pct": 100.0,
        }

    def tank_capacity_liters(self) -> float:
        """Full reservoir capacity in liters from tank dimensions
        (width x length x height, cm). Used to size dosing amounts."""
        t = self.water_tank
        return round(t["width_cm"] * t["length_cm"] * t["height_cm"] / 1000.0, 2)

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
                "targets": self._targets,
                "auto_rules": self.auto_rules,
                "pumps": self.pumps,
                "offsets": self.offsets,
                "hidden_profiles": list(self.hidden_profiles),
                "water_tank": self.water_tank,
                "growth": self.growth,
                "language": self.language,
                "llm_model": self.llm_model,
            }
        )
