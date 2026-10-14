"""Runtime extension seam for additional agents (independent of the ACP transport)."""

from __future__ import annotations

from typing import Protocol

from ...schemas import ProviderSnapshot


class AgentRuntime(Protocol):
    def payload(self, *, ensure_profiles: bool = False) -> dict: ...
    def snapshot(self, profile_id: str, *, role: str) -> ProviderSnapshot: ...
    def verify_snapshot(self, expected: ProviderSnapshot, *, role: str) -> None: ...


RUNTIME_FACTORIES: dict[str, type[AgentRuntime]] = {}
