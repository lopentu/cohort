"""COHORT: evidential pluralism made auditable."""

__version__ = "0.1.0"

from .errors import CohortError
from .eventlog import EventLog, read_events
from .graph import Graph
from .schemas import (
    RESEARCHER,
    Authorship,
    ClaimPayload,
    ConjecturePayload,
    Dating,
    DatingRoute,
    DecisionPayload,
    Edge,
    EdgeType,
    Event,
    IndependentSupport,
    Node,
    NodeStatus,
    NodeType,
    PassagePayload,
    QueryPayload,
    RebuildReport,
    WitnessPayload,
)

__all__ = [
    "RESEARCHER",
    "Authorship",
    "ClaimPayload",
    "CohortError",
    "ConjecturePayload",
    "Dating",
    "DatingRoute",
    "DecisionPayload",
    "Edge",
    "EdgeType",
    "Event",
    "EventLog",
    "Graph",
    "IndependentSupport",
    "Node",
    "NodeStatus",
    "NodeType",
    "PassagePayload",
    "QueryPayload",
    "RebuildReport",
    "WitnessPayload",
    "read_events",
]
