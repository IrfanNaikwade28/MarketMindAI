"""
app/orchestrator/debate_engine.py
----------------------------------
DebateOrchestrator — the core debate controller.

Implements the full Observe → Debate → Decide flow:

  Stage 0: validate_context     → check all required fields present
  Stage 1: trend_stage          → TrendAgent proposes content angle
  Stage 2: brand_stage          → BrandAgent reviews brand alignment
  Stage 3: risk_stage           → RiskAgent evaluates safety
  Stage 4: engagement_stage     → EngagementAgent predicts performance
  Stage 5: cmo_stage            → CMOAgent makes final decision
  Stage 6: mentor_stage         → MentorAgent reviews debate quality

Each stage:
  1. Runs the agent
  2. Appends the output to the shared history (for multi-turn LLM context)
  3. Pushes a WebSocket event to the queue
  4. Returns the updated DebateState

The orchestrator is purely functional — it does NOT touch the database.
Persistence is handled by debate_persistence.py, called from the API layer.
This keeps the engine testable without a DB connection.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Any, AsyncIterator, Callable

from loguru import logger

from app.agents import (
    TrendAgent, BrandAgent, RiskAgent,
    EngagementAgent, CMOAgent, MentorAgent,
    AgentResponse,
)
from app.orchestrator.debate_state import DebateState, build_initial_state
from app.services.content_generator import generate_content, content_to_dict
from app.services.bluesky_service import build_bluesky_post
from app.services.image_service import generate_image, pick_best_image_prompt


# ── Agent singletons (instantiated once, reused across debates) ─
_trend_agent      = TrendAgent()
_brand_agent      = BrandAgent()
_risk_agent       = RiskAgent()
_engagement_agent = EngagementAgent()
_cmo_agent        = CMOAgent()
_mentor_agent     = MentorAgent()


# ── WebSocket event builder ─────────────────────────────────────
def _ws_event(
    agent_name: str,
    action: str,
    message: str,
    stage: str,
    scores: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standardised WebSocket payload for frontend streaming."""
    return {
        "type": "agent_message",
        "stage": stage,
        "agent": agent_name,
        "action": action,
        "message": message,
        "scores": scores or {},
        "extra": extra or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _response_to_dict(response: AgentResponse) -> dict[str, Any]:
    """Convert AgentResponse dataclass → plain dict for JSON storage."""
    d = asdict(response)
    # Convert enum values to strings for JSON serialization
    d["agent_name"] = response.agent_name.value
    d["action"] = response.action.value
    return d


class DebateOrchestrator:
    """
    Runs a full multi-agent debate for a given campaign.

    Usage:
        orchestrator = DebateOrchestrator()

        # Streaming (WebSocket):
        async for event in orchestrator.run_stream(state):
            await websocket.send_json(event)

        # Non-streaming (background task):
        final_state = await orchestrator.run(state)
    """

    def __init__(
        self,
        on_agent_complete: Callable[[DebateState, AgentResponse], None] | None = None,
    ) -> None:
        """
        Args:
            on_agent_complete: Optional callback called after each agent finishes.
                               Used by the persistence layer to save logs immediately.
        """
        self.on_agent_complete = on_agent_complete

    # ── Main entry point ────────────────────────────────────────
    async def run(self, state: DebateState) -> DebateState:
        """
        Execute the full debate synchronously.
        Returns the final DebateState with all agent outputs populated.
        """
        state["status"] = "in_progress"
        state["started_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Debate started | session={} | campaign='{}'",
            state["session_id"], state["campaign_title"]
        )

        try:
            state = await self._stage_trend(state)
            state = await self._stage_brand(state)
            state = await self._stage_risk(state)

            # Early exit if CMO auto-rejected due to critical risk
            if state.get("status") == "vetoed":
                state = await self._stage_mentor(state)
                return self._finalize(state)

            state = await self._stage_engagement(state)
            state = await self._stage_cmo(state)
            state = await self._stage_mentor(state)

            # Generate platform-specific content if approved
            if state.get("outcome") in ("approved", "approved_modified"):
                state = await self._stage_content(state)

        except Exception as e:
            logger.error("Debate engine crashed: {}", e)
            state["status"] = "failed"
            state["error"] = str(e)

        return self._finalize(state)

    # ── Streaming entry point ────────────────────────────────────
    async def run_stream(self, state: DebateState) -> AsyncIterator[dict[str, Any]]:
        """
        Execute the debate and yield WebSocket events as each agent finishes.
        Caller does:
            async for event in orchestrator.run_stream(state):
                await ws.send_json(event)
        """
        state["status"] = "in_progress"
        state["started_at"] = datetime.now(timezone.utc).isoformat()

        yield _ws_event(
            "system", "start", f"Debate started for '{state['campaign_title']}'",
            stage="init",
            extra={"session_id": state["session_id"]},
        )

        stages = [
            self._stage_trend,
            self._stage_brand,
            self._stage_risk,
        ]

        for stage_fn in stages:
            state = await stage_fn(state)
            # Drain the ws queue and yield each event
            while state["websocket_queue"]:
                yield state["websocket_queue"].pop(0)

            # If vetoed at risk stage, skip to mentor
            if state.get("status") == "vetoed":
                break

        if state.get("status") != "vetoed":
            for stage_fn in [self._stage_engagement, self._stage_cmo]:
                state = await stage_fn(state)
                while state["websocket_queue"]:
                    yield state["websocket_queue"].pop(0)

        # Always run mentor
        state = await self._stage_mentor(state)
        while state["websocket_queue"]:
            yield state["websocket_queue"].pop(0)

        # Generate platform content if approved
        if state.get("outcome") in ("approved", "approved_modified"):
            state = await self._stage_content(state)
            while state["websocket_queue"]:
                yield state["websocket_queue"].pop(0)

        state = self._finalize(state)

        yield _ws_event(
            "system", "complete",
            f"Debate complete | outcome: {state.get('outcome', 'unknown')}",
            stage="done",
            extra={
                "outcome": state.get("outcome"),
                "status": state.get("status"),
                "session_id": state["session_id"],
            },
        )

    # ── Stage implementations ────────────────────────────────────

    async def _stage_trend(self, state: DebateState) -> DebateState:
        state["current_stage"] = "trend"
        logger.info("Stage 1/6: TrendAgent")

        context = self._build_context(state)
        response = await _trend_agent.run(context, history=state.get("history", []))

        state["trend_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        # Append agent turn to history for next agents
        self._append_history(state, response, "Stage 1 — Trend Analysis")

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="trend",
            scores={
                "confidence": response.confidence_score,
                "engagement": response.engagement_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_brand(self, state: DebateState) -> DebateState:
        state["current_stage"] = "brand"
        logger.info("Stage 2/6: BrandAgent")

        context = self._build_context(state)
        response = await _brand_agent.run(context, history=state.get("history", []))

        state["brand_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        self._append_history(state, response, "Stage 2 — Brand Review")

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="brand",
            scores={
                "confidence": response.confidence_score,
                "brand_alignment": 1.0 - response.risk_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_risk(self, state: DebateState) -> DebateState:
        state["current_stage"] = "risk"
        logger.info("Stage 3/6: RiskAgent")

        context = self._build_context(state)
        response = await _risk_agent.run(context, history=state.get("history", []))

        state["risk_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        self._append_history(state, response, "Stage 3 — Risk Assessment")

        # Check for critical risk — veto debate only on genuinely dangerous score.
        # is_approved from the LLM is informational only; it is NOT a veto gate
        # because the LLM tends to set it false for minor concerns. Only an
        # objectively high risk_score (>= 0.85) triggers an automatic veto.
        risk_score = response.risk_score

        if risk_score >= 0.85:
            logger.warning(
                "DEBATE VETOED by Risk Agent | risk_score={:.0%}", risk_score
            )
            state["status"] = "vetoed"
            state["outcome"] = "rejected"

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="risk",
            scores={
                "risk": response.risk_score,
                "confidence": response.confidence_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_engagement(self, state: DebateState) -> DebateState:
        state["current_stage"] = "engagement"
        logger.info("Stage 4/6: EngagementAgent")

        context = self._build_context(state)
        response = await _engagement_agent.run(context, history=state.get("history", []))

        state["engagement_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        self._append_history(state, response, "Stage 4 — Engagement Prediction")

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="engagement",
            scores={
                "engagement": response.engagement_score,
                "confidence": response.confidence_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_cmo(self, state: DebateState) -> DebateState:
        state["current_stage"] = "cmo"
        logger.info("Stage 5/6: CMOAgent")

        context = self._build_context(state)
        response = await _cmo_agent.run(context, history=state.get("history", []))

        state["cmo_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        self._append_history(state, response, "Stage 5 — CMO Decision")

        # Map CMO decision to debate outcome
        cmo_decision = response.structured_output.get("decision", "approved_modified")
        outcome_map = {
            "approved":          "approved",
            "approved_modified": "approved_modified",
            "rejected":          "rejected",
        }
        state["outcome"] = outcome_map.get(cmo_decision, "approved_modified")

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="cmo",
            scores={
                "composite": response.structured_output.get("composite_score", 0.0),
                "confidence": response.confidence_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_mentor(self, state: DebateState) -> DebateState:
        state["current_stage"] = "mentor"
        logger.info("Stage 6/6: MentorAgent")

        context = self._build_context(state)
        response = await _mentor_agent.run(context, history=state.get("history", []))

        state["mentor_agent_output"] = _response_to_dict(response)
        state["sequence_counter"] = state.get("sequence_counter", 0) + 1

        self._append_history(state, response, "Stage 6 — Mentor Review")

        state["websocket_queue"].append(_ws_event(
            agent_name=response.agent_name.value,
            action=response.action.value,
            message=response.message,
            stage="mentor",
            scores={
                "debate_quality": response.engagement_score,
                "confidence": response.confidence_score,
            },
            extra=response.structured_output,
        ))

        if self.on_agent_complete:
            self.on_agent_complete(state, response)

        return state

    async def _stage_content(self, state: DebateState) -> DebateState:
        """
        Stage 7 (optional): Content Generation + Human Approval Gate
        Runs after CMO approval.

        Steps:
          1. Call ContentGenerator for each target platform (all concurrent).
          2. Store all generated content dicts in state['generated_content'].
          3. Build a rich Bluesky draft post via build_bluesky_post().
          4. Store draft in state['pending_approval'] and emit a
             'pending_approval' WebSocket event — then STOP.
             The actual publish happens only after the human approves via
             POST /debates/{session_id}/approve.
        """
        state["current_stage"] = "content_generation"
        logger.info("Stage 7: ContentGenerator + waiting for human approval")

        # ── Step 1 & 2: Generate platform content ───────────────
        try:
            results = await generate_content(state)
            content_dicts = [content_to_dict(r) for r in results]
            state["generated_content"] = content_dicts

            success_count = sum(1 for r in results if r.success)
            state["websocket_queue"].append(_ws_event(
                agent_name="system",
                action="generate",
                message=(
                    f"Content generated for {success_count}/{len(results)} platforms: "
                    + ", ".join(r.platform for r in results if r.success)
                ),
                stage="content_generation",
                extra={"platforms": [r.platform for r in results if r.success]},
            ))

        except Exception as e:
            logger.error("ContentGenerator stage failed: {}", e)
            content_dicts = []
            state["generated_content"] = []
            state["websocket_queue"].append(_ws_event(
                agent_name="system",
                action="error",
                message=f"Content generation failed: {e}",
                stage="content_generation",
            ))

        # ── Step 3 & 4: Build draft post and gate on human approval ─
        if content_dicts:
            try:
                draft_text = await build_bluesky_post(content_dicts, state=state)

                # ── Generate image upfront so it can be shown in the modal ──
                image_b64: str = ""
                image_prompt: str = pick_best_image_prompt(content_dicts)
                if image_prompt:
                    logger.info(
                        "_stage_content | generating image for approval preview | prompt_len={}",
                        len(image_prompt),
                    )
                    image_bytes = await generate_image(image_prompt)
                    if image_bytes:
                        import base64 as _b64
                        image_b64 = _b64.b64encode(image_bytes).decode("ascii")
                        logger.info(
                            "_stage_content | image ready | b64_len={}",
                            len(image_b64),
                        )
                    else:
                        logger.warning("_stage_content | image generation returned None — no preview")

                state["pending_approval"] = {
                    "draft_post":        draft_text,
                    "generated_content": content_dicts,
                    "image_b64":         image_b64,
                    "image_prompt":      image_prompt,
                }

                logger.info(
                    "Human approval gate | session={} | draft_length={}",
                    state["session_id"], len(draft_text),
                )

                state["websocket_queue"].append({
                    "type":              "pending_approval",
                    "stage":             "human_approval",
                    "draft_post":        draft_text,
                    "generated_content": content_dicts,
                    "session_id":        state["session_id"],
                    "image_b64":         image_b64,
                    "timestamp":         __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                })

            except Exception as e:
                logger.error("Build draft post failed: {}", e)
                state["websocket_queue"].append(_ws_event(
                    agent_name="system",
                    action="error",
                    message=f"Draft post build failed: {e}",
                    stage="human_approval",
                ))
        else:
            state["websocket_queue"].append(_ws_event(
                agent_name="system",
                action="warning",
                message="No content generated — skipping human approval gate.",
                stage="human_approval",
            ))

        return state

    # ── Helpers ─────────────────────────────────────────────────

    def _build_context(self, state: DebateState) -> dict[str, Any]:
        """
        Build the context dict passed to each agent's run() method.
        Includes campaign info + all prior agent outputs.
        """
        return {
            "campaign_title":           state.get("campaign_title", ""),
            "campaign_goal":            state.get("campaign_goal", ""),
            "brand_name":               state.get("brand_name", ""),
            "brand_voice":              state.get("brand_voice", ""),
            "target_audience":          state.get("target_audience", ""),
            "brand_guidelines":         state.get("brand_guidelines", ""),
            "keywords":                 state.get("keywords", []),
            "platforms":                state.get("platforms", []),
            # Agent outputs (populated as debate progresses)
            "trend_agent_output":       state.get("trend_agent_output", {}),
            "brand_agent_output":       state.get("brand_agent_output", {}),
            "risk_agent_output":        state.get("risk_agent_output", {}),
            "engagement_agent_output":  state.get("engagement_agent_output", {}),
            "cmo_agent_output":         state.get("cmo_agent_output", {}),
        }

    def _append_history(
        self,
        state: DebateState,
        response: AgentResponse,
        stage_label: str,
    ) -> None:
        """
        Append the agent's response to the shared conversation history
        so subsequent agents have full context of what's been said.
        """
        state["history"].append({
            "role": "assistant",
            "content": (
                f"[{stage_label}] {response.agent_name.value.upper()}: "
                f"{response.message}"
            ),
        })

    def _finalize(self, state: DebateState) -> DebateState:
        """Mark the debate as completed and set the completed_at timestamp."""
        if state.get("status") not in ("failed", "vetoed"):
            state["status"] = "completed"
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["current_stage"] = "done"
        logger.info(
            "Debate finalized | status={} | outcome={}",
            state["status"], state.get("outcome", "N/A")
        )
        return state
