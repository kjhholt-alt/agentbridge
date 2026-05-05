"""AgentBridge Python harness.

Phase 4: typed client (sync + async), replay verifier, orchestrator,
and `agentbridge` CLI all live here.
"""

from .client import Client, AsyncClient, BridgeError, HelloResponse, PROTOCOL_VERSION
from .replay import verify, record, DivergenceReport

__version__ = "0.1.0"
__protocol_version__ = PROTOCOL_VERSION

__all__ = [
    "Client", "AsyncClient", "BridgeError", "HelloResponse",
    "PROTOCOL_VERSION", "verify", "record", "DivergenceReport",
]
