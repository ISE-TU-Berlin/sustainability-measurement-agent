"""
Core data models and protocols for SMA.

This module contains all dataclasses and protocol definitions that can be
safely imported throughout the codebase without circular import issues.
Config classes are kept separate in config.py.
"""
import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Any
import pandas as pd


# ============================================================================
# Protocols
# ============================================================================

class SMAMetadata(Protocol):
    """Protocol for metadata objects that can be serialized to dict."""
    def to_dict(self, kwargs: Optional[dict]) -> dict:
        ...


class DataframeResource(Protocol):
    """Protocol for resources that can be converted to pandas DataFrames."""
    def to_dataframe(self) -> pd.DataFrame:
        pass


class SMAObserver(Protocol):
    """Observer protocol for SMA lifecycle events."""
    def onSetup(self) -> None:
        pass

    def onLeft(self) -> None:
        pass

    def onStart(self) -> None:
        pass

    def onEnd(self) -> None:
        pass

    def onRight(self) -> None:
        pass

    def onTeardown(self) -> None:
        pass


class TriggerFunction(Protocol):
    """Protocol for trigger functions that initiate measurements."""
    def __call__(self) -> Optional[dict]:
        pass


class EnvironmentCollector(Protocol):
    """Protocol for environment data collectors."""
    def observe_environment(self, run: "SMARun") -> "Environment":
        pass


# ============================================================================
# Report Models
# ============================================================================

@dataclass
class SMASession:
    """
    Metadata about the measurement session (initialized once when an SMA agent is created).
    """
    name: str
    extras: Optional[dict] = None

    def to_dict(self, kwargs: Optional[dict]) -> dict:
        meta = {
            "session": self.name,
        }

        # Merge extras at top level for template substitution
        if self.extras:
            meta.update(self.extras)

        if kwargs:
            meta.update(kwargs)
        return meta


@dataclass
class SMARun:
    """
    Metadata about a specific measurement run.
    """
    startTime: datetime.datetime
    endTime: datetime.datetime
    treatment_start: datetime.datetime
    treatment_end: datetime.datetime
    runHash: str
    user_data: Optional[dict] = None

    def duration(self) -> datetime.timedelta:
        return self.endTime - self.startTime

    def treatment_duration(self) -> datetime.timedelta:
        return self.treatment_end - self.treatment_start

    def to_dict(self, kwargs: Optional[dict]) -> dict:
        meta = {
            "startTime": self.startTime.strftime("%Y_%m_%d_%H_%M_%S"),
            "endTime": self.endTime.strftime("%Y_%m_%d_%H_%M_%S") if self.endTime is not None else "",
            "treatment_start": self.treatment_start.strftime("%Y_%m_%d_%H_%M_%S") if self.treatment_start is not None else "",
            "treatment_end": self.treatment_end.strftime("%Y_%m_%d_%H_%M_%S") if self.treatment_end is not None else "",
            "runHash": self.runHash,
            "duration": self.duration().total_seconds() if self.duration() is not None else "",  # type: ignore
            "treatment_duration": self.treatment_duration().total_seconds() if self.treatment_duration() is not None else "",  # type: ignore
            "user_data": self.user_data if self.user_data is not None else {},
        }

        if kwargs:
            meta.update(kwargs)
        return meta

    @staticmethod
    def fields() -> List[str]:
        return [
            "startTime",
            "endTime",
            "treatment_start",
            "treatment_end",
            "runHash",
            "duration",
            "treatment_duration",
            "user_data"
        ]


@dataclass
class ReportMetadata:
    """Combined metadata for a report (session + run)."""
    session: SMASession
    run: SMARun

    def to_dict(self, kwargs: Optional[dict] = None) -> dict:
        meta = {}
        meta.update(self.session.to_dict({}))
        meta.update(self.run.to_dict({}))
        if kwargs:
            meta.update(kwargs)
        return meta


# ============================================================================
# Observation Models
# ============================================================================

@dataclass
class ObservationTarget:
    """Target specification for observations (based on Kubernetes label selectors)."""
    match_labels: Optional[dict] = None
    match_expressions: Optional[list] = None


@dataclass
class ObservationWindow:
    """Time window configuration for observations."""
    left: int
    right: int
    duration: int


@dataclass
class ObservationEnvironmentConfig:
    """Configuration for environment observation."""
    collector: str


@dataclass
class ObservationConfig:
    """Configuration for observation behavior."""
    mode: str
    window: Optional[ObservationWindow]
    targets: Optional[List[ObservationTarget]] = None
    environment: Optional[ObservationEnvironmentConfig] = None


# ============================================================================
# Environment Models
# ============================================================================

class EphemeralResource:
    """Base class for resources with a lifecycle."""
    lifetime_start: datetime.datetime
    lifetime_end: Optional[datetime.datetime] = None
    events: Optional[pd.Series] = None


@dataclass
class Node(DataframeResource):
    """Kubernetes node representation."""
    name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        df_structure = []
        for k, v in self.labels.items():
            df_structure.append((self.name, k, v))
        return pd.DataFrame(df_structure, columns=["node", "label", "value"])


@dataclass
class Pod(EphemeralResource, DataframeResource):
    """Kubernetes pod representation."""
    name: str
    namespace: str
    node_name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        df_structure = [(self.name, self.namespace, self.node_name, self.lifetime_start,
                        self.lifetime_end, self.events, self.labels)]
        return pd.DataFrame(df_structure, columns=["pod", "namespace", "node",
                                                   "lifetime_start", "lifetime_end",
                                                   "events", "labels"])


@dataclass
class Container(EphemeralResource, DataframeResource):
    """Kubernetes container representation."""
    name: str
    pod_name: str
    namespace: str
    node_name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        df_structure = [(self.name, self.pod_name, self.namespace, self.node_name,
                        self.lifetime_start, self.lifetime_end, self.events, self.labels)]
        return pd.DataFrame(df_structure, columns=["container", "pod", "namespace", "node",
                                                   "lifetime_start", "lifetime_end",
                                                   "events", "labels"])


class Process(EphemeralResource, DataframeResource):
    """Process representation."""
    pid: int
    name: str
    container_name: Optional[str] = None
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    node_name: Optional[str] = None

    def to_dataframe(self) -> pd.DataFrame:
        df_structure = [(self.pid, self.name, self.container_name, self.pod_name,
                        self.namespace, self.node_name, self.lifetime_start,
                        self.lifetime_end, self.events)]
        return pd.DataFrame(df_structure, columns=["pid", "name", "container", "pod",
                                                   "namespace", "node", "lifetime_start",
                                                   "lifetime_end", "events"])


# ============================================================================
# Config Models (non-Config dataclasses)
# ============================================================================

@dataclass
class ReportConfig:
    """Configuration for report generation and storage."""
    format: str = "csv"
    location: str = "reports/${startTime}_${runHash}/"
    filename: str = "${name}.csv"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportConfig":
        """Create ReportConfig from a dictionary."""
        return cls(
            format=data.get("format", "csv"),
            location=data.get("location", "reports/${startTime}_${runHash}/"),
            filename=data.get("filename", "${name}.csv")
        )


@dataclass
class MeasurementConfig:
    """Configuration for a single measurement."""
    name: str
    type: str
    query: str
    step: int = 60
    layer: Optional[str] = None
    unit: Optional[str] = None
    target_names: Optional[List[str]] = None

