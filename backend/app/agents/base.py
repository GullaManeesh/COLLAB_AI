from abc import ABC, abstractmethod
from typing import Any


class Agent(ABC):
    """Common execution boundary for authenticated agents."""

    agent_type: str

    @abstractmethod
    async def execute(self, *, workspace_id: str, user: dict[str, Any], content: str, exclude_message_id=None):
        """Run an agent using only data available to the authenticated workspace member."""
        raise NotImplementedError
