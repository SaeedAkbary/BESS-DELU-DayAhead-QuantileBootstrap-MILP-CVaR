"""Strict JSON configuration for reproducible illustrative experiments."""
import json
import math
from pathlib import Path
from battery_optimization import Battery


DEFAULT_BATTERY = dict(capacity_mwh=2., power_mw=1., eta_charge=.95,
                       eta_discharge=.95, initial_mwh=1.)
DEFAULTS = dict(alpha=.95, seed=42, scenario_count=50, volatility_scale=1.,
                selection_rule="profit", downside_penalty=0., lookback_months=None)


def validate_config(raw):
    allowed = {*DEFAULTS, "battery", "economic_parameters_status", "source_provenance", "experiments"}
    if set(raw) - allowed:
        raise ValueError(f"Unknown configuration fields: {set(raw) - allowed}")
    config = {**DEFAULTS, **raw}
    battery = Battery(**{**DEFAULT_BATTERY, **raw.get("battery", {})})
    battery.validate()
    if battery.terminal_mwh not in (None, battery.initial_mwh):
        raise ValueError("Commercial backtests require daily cyclic SOC")
    config["battery"] = vars(battery)
    if not 0 < config["alpha"] < 1:
        raise ValueError("Invalid alpha")
    for key in ("scenario_count", "seed"):
        if isinstance(config[key], bool) or not isinstance(config[key], int):
            raise ValueError(f"{key} must be an integer")
    if config["scenario_count"] < 2 or config["seed"] < 0:
        raise ValueError("scenario_count >= 2 and seed >= 0 required")
    for key in ("volatility_scale", "downside_penalty"):
        if not math.isfinite(config[key]) or config[key] < 0:
            raise ValueError(f"Invalid {key}")
    if config["volatility_scale"] == 0:
        raise ValueError("volatility_scale must be positive")
    if config["selection_rule"] not in ("profit", "net_downside"):
        raise ValueError("Unknown selection rule")
    lookback = config["lookback_months"]
    if lookback is not None and (isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1):
        raise ValueError("lookback_months must be a positive integer")
    return config


def load_config(path=None):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")) if path else {})


def experiment_configs(config):
    """OAT = one changed parameter; joint stress = explicitly grouped changes."""
    base = validate_config(config)
    experiments = base.pop("experiments", [])
    yield "base", "baseline", base
    names = {"base"}
    for experiment in experiments:
        if set(experiment) != {"name", "kind", "overrides"}:
            raise ValueError("Experiments require name, kind and overrides")
        name, kind, changes = experiment["name"], experiment["kind"], experiment["overrides"]
        if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name) or name in names:
            raise ValueError("Experiment names must be unique safe lowercase identifiers")
        names.add(name)
        if kind not in ("one_at_a_time", "joint_stress") or not changes:
            raise ValueError("Invalid experiment kind or empty overrides")
        if kind == "one_at_a_time" and len(changes) != 1:
            raise ValueError("One-at-a-time experiments change exactly one parameter")
        altered = {**base, "battery": dict(base["battery"])}
        for field, value in changes.items():
            if field == "round_trip_efficiency":
                if not math.isfinite(value) or not 0 < value <= 1:
                    raise ValueError("Round-trip efficiency must be in (0,1]")
                altered["battery"].update(eta_charge=math.sqrt(value), eta_discharge=math.sqrt(value))
            elif field in altered["battery"]:
                altered["battery"][field] = value
            elif field in DEFAULTS:
                altered[field] = value
            else:
                raise ValueError(f"Unknown experiment parameter: {field}")
        yield name, kind, validate_config(altered)
