
"""Configuration loader for the Sustainability Measurement Agent (SMA).

This module provides a small, dependency-light loader for the YAML config
format used in `examples/minimal.yml`. It intentionally defers importing
PyYAML until `from_file` is called so importing this module doesn't require
the YAML package to be installed.

It maps:
- services.prometheus -> PrometheusServiceConfig
- observation -> ObservationConfig (and named ObservationTarget instances)
- measurements -> MeasurementConfig

The loader also provides conveniences to construct a Prometheus client and
convert measurements into `PrometheusQuery` objects.

Aided by AI.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

# Local imports (kept light). Prometheus and PrometheusQuery are used only at
# runtime when building queries; importing this module should not force heavy
# runtime dependencies beyond the package itself.
from sma.prometheus import Prometheus, PrometheusMetric
from sma.service import ServiceClient
from sma.observations import ObservationTarget, ObservationWindow, ObservationConfig

from typing import Optional, List



def _parse_duration(value: Optional[Any]) -> int:
    """Parse a duration string like '10m', '420s', '1h30m' into seconds.

    Accepts integers (returned as-is) and returns 0 for None.
    """
    if value is None:
        return 0
    if isinstance(value, int):
        return int(value)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    total = 0
    pattern = re.compile(r"^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)m)?(?:(?P<s>\d+)s)?$")
    m = pattern.match(s)
    if not m:
        raise ValueError(f"Unsupported duration format: {value}")
    if m.group("h"):
        total += int(m.group("h")) * 3600
    if m.group("m"):
        total += int(m.group("m")) * 60
    if m.group("s"):
        total += int(m.group("s"))
    return total




@dataclass
class MeasurementConfig:
    name: str
    type: str
    query: str
    step: int = 60
    layer: Optional[str] = None
    target_names: Optional[List[str]] = None

    def to_prometheus_query(self, name: str, client: Prometheus, named_targets: Dict[str, ObservationTarget]) -> PrometheusMetric:
        targets: List[ObservationTarget] = []
        if not self.target_names:
            targets = []
        elif "all" in self.target_names:
            targets = list(named_targets.values())
        else:
            for tname in self.target_names:
                if tname not in named_targets:
                    raise KeyError(f"measurement {self.name} references unknown target '{tname}'")
                targets.append(named_targets[tname])

        return PrometheusMetric(
            client=client,
            name=name,
            query=self.query,
            layer=self.layer,
            query_type=self.type,
            step=self.step,
            targets=targets,
        )


class Config:
    def __init__(self, version: Optional[str], services: Dict[str, ServiceClient], observation: ObservationConfig, measurements: Dict[str, MeasurementConfig], report: Dict[str, Any]):
        self.version = version
        self.services = services
        self.observation = observation
        self.measurements = measurements
        self.report = report
        # runtime caches
        self._named_targets: Dict[str, ObservationTarget] = {}

    @classmethod
    def from_file(cls, path: str) -> "Config":
        # Lazy import of PyYAML so importing this module doesn't require it.
        try:
            import yaml  # type: ignore
        except Exception as e:
            raise ImportError(
                "PyYAML is required to load configuration. Install it with: pipenv install PyYAML"
            ) from e

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Config":
        if not isinstance(raw, dict) or "sma" not in raw:
            raise ValueError("Invalid configuration: expected top-level 'sma' key")

        sma = raw.get("sma") or {}
        version = sma.get("version")

        # Services
        services_cfg: Dict[str, Any] = {}
        services_raw = sma.get("services", {}) or {}
        # Mapping of service name to config class or factory
        service_class_map = {
            "prometheus": Prometheus,
            # Add more mappings here as new services are supported
        }
        for service_name, service_conf in services_raw.items():
            conf = service_conf or {}
            if not isinstance(conf, dict):
                raise ValueError(f"service '{service_name}' configuration must be a mapping")

            factory = service_class_map.get(service_name)
            if factory is None:
                raise ValueError(f"Unknown service '{service_name}' in config. Supported: {list(service_class_map.keys())}")

            if not callable(factory):
                raise ValueError(f"Configured factory for service '{service_name}' is not callable")

            try:
                services_cfg[service_name] = factory(conf)
            except TypeError as te:
                raise ValueError(f"Failed to instantiate service '{service_name}' with config {conf}: {te}") from te
            except ValueError:
                # Re-raise ValueError from service constructor to surface missing/invalid fields
                raise

        # Observation
        obs_raw = sma.get("observation", {}) or {}
        mode = obs_raw.get("mode", "timer")  # default to 'timer' mode
        window_raw = obs_raw.get("window", {}) or {}
        window = None
        if len(window_raw) == 0:
            if mode == "window":
                raise ValueError("observation mode 'window' requires a 'window' configuration")
        else:
            window = ObservationWindow(
                left=_parse_duration(window_raw.get("left")),
                right=_parse_duration(window_raw.get("right")),
                duration=_parse_duration(window_raw.get("duration")),
            )

        targets_list = obs_raw.get("targets", []) or []
        named_targets: Dict[str, ObservationTarget] = {}
        for t in targets_list:
            if not isinstance(t, dict):
                raise ValueError("each target must be a mapping with at least a 'name' entry")
            name = t.get("name")
            if not name:
                raise ValueError("each target must have a 'name'")
            namespace = t.get("namespace")
            selector = t.get("selector") or {}
            match_labels = {}
            if isinstance(selector, dict):
                match_labels = selector.get("matchLabels", {}) or selector.get("match_labels", {})
            match_labels["namespace"] = namespace
            ot = ObservationTarget(match_labels=match_labels)
            named_targets[name] = ot
        observation = ObservationConfig(mode=mode, window=window, targets=list(named_targets.values()))

        # Measurements
        measurements_raw = sma.get("measurements", []) or []
        measurements: Dict[str, MeasurementConfig] = {}
        for m in measurements_raw:
            if not isinstance(m, dict) or len(m) != 1:
                raise ValueError("each measurement entry must be a single-key mapping where the key is the measurement name")
            name = list(m.keys())[0]
            body = m[name] or {}
            mtype = body.get("type", "aggregate")
            layer = body.get("layer")
            query = body.get("query")
            if not query:
                raise ValueError(f"measurement '{name}' missing required 'query'")
            step = int(body.get("step", 60))
            target_names = body.get("target") or body.get("targets") or []
            if isinstance(target_names, str):
                target_names = [target_names]
            measurements[name] = MeasurementConfig(name=name, type=mtype, query=query, step=step, layer=layer, target_names=target_names)

        report = sma.get("report", {}) or {}

        cfg = cls(version=version, services=services_cfg, observation=observation, measurements=measurements, report=report)
        cfg._named_targets = named_targets
        return cfg

    def prometheus_client(self) -> Optional[Prometheus]:
        svc = self.services.get("prometheus")
        if svc is None:
            return None
        return svc # type: ignore

    def measurement_queries(self) -> Dict[str, PrometheusMetric]:
        client = self.prometheus_client()
        if client is None:
            raise RuntimeError("no prometheus service configured")
        out: Dict[str, PrometheusMetric] = {}
        for name, m in self.measurements.items():
            out[name] = m.to_prometheus_query(name=name, client=client, named_targets=self._named_targets)
        return out

