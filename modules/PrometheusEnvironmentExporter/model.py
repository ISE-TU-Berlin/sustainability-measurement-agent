import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple, Protocol
from dataclasses import dataclass

import pandas as pd
from sma.model import SMARun

class EnvironmentCollector(Protocol):
    """Protocol for environment data collectors."""
    def observe_environment(self, run: SMARun) -> "Environment":
        pass



class DataframeResource(Protocol):
    """Protocol for resources that can be converted to pandas DataFrames."""
    def to_dataframe(self) -> pd.DataFrame:
        pass


# ============================================================================
# Environment Models
# ============================================================================

class EphemeralResource:
    """Base class for resources with a lifecycle."""
    lifetime_start: datetime.datetime
    lifetime_end: Optional[datetime.datetime] = None
    events: Optional[Tuple[datetime.datetime, str]] = None

def explode_labels(rows: List[List[any]], columns: List[str], labels: Dict[str, str]) -> Tuple[List[List[any]],List[str]]:
    """
           adds labels to all provided rows and retunrs an updated columns list and data
    """
    _columns = []
    for k in labels.keys():
        if k not in columns:
            _columns.append(k)

    def add_labels(row):
        for k in _columns:
            #we need to preseve order...
            row.append(labels[k])

    _rows = []
    for row in rows:
        _row = row.copy()
        add_labels(_row)
        _rows.append(_row)
    _columns = [*columns, *_columns]
    return _rows, list(_columns)


@dataclass
class Node(DataframeResource):
    """Kubernetes node representation."""
    name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        rows, columns = explode_labels( [[self.name]],["name"], self.labels)
        return pd.DataFrame(rows, columns=columns)

def explode_events(rows: List[List[any]], columns: List[str], events: Optional[Tuple[datetime.datetime, str]]) -> Tuple[List[List[any]],List[str]]:
    """
       adds events to all provided rows and retunrs an updated data
    """

    _rows = []
    if events is None:
        events = [(None, None)]
    for event in events:
        for row in rows:
            _rows.append([*row, event[1], event[0]])

    return _rows, [*columns, "event", "event_time"]

@dataclass
class Pod(EphemeralResource, DataframeResource):
    """Kubernetes pod representation."""
    name: str
    namespace: str
    node_name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        cols = ["pod", "namespace", "node", "lifetime_start", "lifetime_end"]
        rows = [[self.name, self.namespace, self.node_name, self.lifetime_start, self.lifetime_end]]

        rows, cols = explode_events(rows, cols, self.events)
        rows, cols = explode_labels( rows,cols, self.labels)

        return  pd.DataFrame(rows, columns=cols)


@dataclass
class Container(EphemeralResource, DataframeResource):
    """Kubernetes container representation."""
    name: str
    pod_name: str
    namespace: str
    node_name: str
    labels: Dict[str, str]

    def to_dataframe(self) -> pd.DataFrame:
        cols = ["name","pod_name","namespace","node_name", "lifetime_start", "lifetime_end"]
        rows = [[self.name, self.pod_name, self.namespace, self.node_name, self.lifetime_start, self.lifetime_end]]

        rows, cols  = explode_events(rows, cols, self.events)
        rows, cols = explode_labels( rows, cols, self.labels)

        return pd.DataFrame(rows, columns=cols)


class Process(EphemeralResource, DataframeResource):
    """Process representation."""
    pid: int
    name: str
    container_name: Optional[str] = None
    pod_name: Optional[str] = None
    namespace: Optional[str] = None
    node_name: Optional[str] = None

    def to_dataframe(self) -> pd.DataFrame:
        cols = ["pid","name", "container_name","pod_name", "namespace", "node_name", "lifetime_start", "lifetime_end", "event",
                   "event_time"]
        row = [[self.pid,self.name,self.container_name,self.pod_name, self.namespace, self.node_name, self.lifetime_start, self.lifetime_end]]

        rows, cols  = explode_events(row, cols, self.events)

        return pd.DataFrame(rows, columns=cols)

