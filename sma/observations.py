from dataclasses import dataclass
from typing import Optional, List
from kubernetes.client.models import V1LabelSelector


@dataclass
class ObservationTarget(V1LabelSelector):
    def __init__(self, match_labels: Optional[dict] = None, match_expressions: Optional[list] = None):
        super().__init__(match_labels=match_labels, match_expressions=match_expressions)

@dataclass
class ObservationWindow:
    left: int
    right: int
    duration: int

@dataclass
class ObservationConfig(object):
    def __init__(self, mode: str, window: ObservationWindow, targets: Optional[List[ObservationTarget]] = None):
        self.mode = mode
        self.window = window
        self.targets = targets if targets is not None else []

