from __future__ import annotations

from typing import Any
from uuid import uuid4


class ActionProposalStore:
    """In-process proposal store for local mode; jobs can replace it with Redis.

    Holds high-risk tool calls (技术设计.md §66) that were intercepted by the
    ToolRegistry pending explicit user confirmation (§67). A proposal is a
    frozen record of the intended call: confirming it executes exactly the
    tool + arguments the user was shown, so the approved action cannot be
    silently swapped between proposal and execution.
    """

    def __init__(self) -> None:
        self._proposals: dict[str, dict[str, Any]] = {}

    def create(
        self,
        user_id: str,
        tool: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
        reason: str = "This action requires explicit user confirmation.",
    ) -> dict[str, Any]:
        proposal = {
            "id": str(uuid4()),
            "user_id": user_id,
            "agent_name": agent_name,
            "tool": tool,
            "arguments": arguments,
            "reason": reason,
            "requires_confirmation": True,
            "status": "PENDING",
        }
        self._proposals[proposal["id"]] = proposal
        return proposal

    def get(self, proposal_id: str, user_id: str) -> dict[str, Any] | None:
        proposal = self._proposals.get(proposal_id)
        if proposal is None or proposal["user_id"] != user_id:
            return None
        return proposal

    def confirm(self, proposal_id: str, user_id: str) -> dict[str, Any] | None:
        """Mark a pending proposal CONFIRMED.

        Returns the proposal so the caller can execute the exact frozen call.
        Idempotent: re-confirming an already CONFIRMED proposal returns it
        unchanged rather than re-running a side effect.
        """
        proposal = self.get(proposal_id, user_id)
        if proposal is None:
            return None
        if proposal["status"] == "PENDING":
            proposal["status"] = "CONFIRMED"
        return proposal

    def reject(self, proposal_id: str, user_id: str) -> dict[str, Any] | None:
        proposal = self.get(proposal_id, user_id)
        if proposal is None:
            return None
        proposal["status"] = "REJECTED"
        return proposal


action_proposals = ActionProposalStore()
