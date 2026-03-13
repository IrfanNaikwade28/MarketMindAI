"""
app/agents/base_agent.py
------------------------
Abstract base class that every agent inherits.

Enforces a common interface:
  - run()  → must be implemented by each agent
  - _chat() → calls Groq with the agent's system prompt
  - _build_messages() → constructs the message list

Every agent returns a typed AgentResponse dataclass
so the orchestrator always gets a consistent structure.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.utils.groq_client import groq_json
from app.models.agent_log import AgentName, AgentAction


@dataclass
class AgentResponse:
    """
    Standardised response every agent must return.

    Fields:
        agent_name       : Which agent produced this
        action           : What kind of contribution this is
        message          : Human-readable summary (shown in UI debate log)
        structured_output: Full JSON payload with all agent-specific fields
        confidence_score : 0.0–1.0 how confident the agent is
        risk_score       : 0.0–1.0 (Risk Agent primary, others secondary)
        engagement_score : 0.0–1.0 predicted engagement
        tokens_used      : Token count from Groq response (for cost tracking)
        success          : False if the agent errored out
        error            : Error message if success=False
    """
    agent_name: AgentName
    action: AgentAction
    message: str
    structured_output: dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    risk_score: float = 0.0
    engagement_score: float = 0.0
    tokens_used: int = 0
    success: bool = True
    error: str | None = None


class BaseAgent(ABC):
    """
    Abstract base for all AI Council agents.

    Each subclass must:
      1. Set `name` (AgentName enum value)
      2. Set `system_prompt` (the agent's persona & instructions)
      3. Implement `run(context)` which returns AgentResponse
    """

    name: AgentName
    system_prompt: str

    def __init__(self) -> None:
        if not hasattr(self, "name") or not hasattr(self, "system_prompt"):
            raise NotImplementedError(
                "Subclasses must define `name` and `system_prompt`"
            )
        logger.debug("Agent initialised: {}", self.name)

    def _build_messages(
        self,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """
        Build the full message list for Groq.

        Args:
            user_prompt : The task/context for this agent's turn
            history     : Optional prior debate messages for context
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_prompt})
        return messages

    async def _chat(
        self,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
    ) -> dict[str, Any]:
        """
        Call Groq in JSON mode and return parsed dict.
        Raises ValueError if the model returns invalid JSON.
        """
        messages = self._build_messages(user_prompt, history)
        result = await groq_json(messages=messages, temperature=temperature)
        return result

    @abstractmethod
    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Execute the agent's task.

        Args:
            context : Dict with campaign info, prior agent outputs, etc.
            history : Prior debate turns for multi-turn awareness

        Returns:
            AgentResponse with structured output
        """
        ...

    def _error_response(self, action: AgentAction, error: Exception) -> AgentResponse:
        """Return a safe fallback AgentResponse when something goes wrong."""
        logger.error("{} failed: {}", self.name, error)
        return AgentResponse(
            agent_name=self.name,
            action=action,
            message=f"{self.name} encountered an error: {error}",
            success=False,
            error=str(error),
        )
