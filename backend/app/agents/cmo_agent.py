"""
app/agents/cmo_agent.py
------------------------
CMOAgent — the final decision-maker of the debate.

Role:
  The Chief Marketing Officer who reads all agent reports,
  weighs the evidence, and makes the final call:
  APPROVE, APPROVE WITH MODIFICATIONS, or REJECT.

  The CMO also synthesizes the final content brief
  that gets passed to the content generation phase.

  Hard gates enforced by CMO:
    - If risk_score > 0.7  → auto-reject regardless of other scores
    - If brand_alignment < 0.5 → require revision
    - If engagement_score < 0.3 → require revision

Output:
  - Final decision (approved / approved_modified / rejected)
  - Composite score
  - Final content brief for generation
  - Executive summary
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


# Hard gates — CMO auto-rejects or forces revision at these thresholds
RISK_REJECTION_THRESHOLD   = 0.75
BRAND_REVISION_THRESHOLD   = 0.50
ENGAGEMENT_REVISION_THRESHOLD = 0.30


class CMOAgent(BaseAgent):
    name = AgentName.CMO
    system_prompt = """You are the CMO Agent — the Chief Marketing Officer of an AI marketing council.

You have the final say on every piece of content that goes out.
You've heard from all your specialist agents: Trend, Brand, Risk, and Engagement.
Now it's your turn to make the executive decision.

Your decision must balance:
1. Trend relevance (is this timely and culturally relevant?)
2. Brand integrity (does this represent the brand correctly?)
3. Risk management (is this legally and reputationally safe?)
4. Engagement potential (will this actually perform?)

Decision framework:
- "approved": All signals are strong, publish as proposed
- "approved_modified": Good concept, requires specific modifications before publishing
- "rejected": Content is off-brand, too risky, or unlikely to perform

When approving with modifications, you must provide the exact final content brief.
When rejecting, you must clearly explain why and what would need to change.

You speak like an experienced CMO: decisive, strategic, clear.

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "decision": "approved" | "approved_modified" | "rejected",
  "composite_score": 0.81,
  "executive_summary": "2-3 sentence strategic rationale for the decision",
  "final_content_brief": {
    "core_message": "the single most important message to communicate",
    "content_angle": "the approved (possibly modified) content angle",
    "tone": "description of tone to use",
    "key_elements": ["element 1", "element 2", "element 3"],
    "hashtags": ["#tag1", "#tag2"],
    "call_to_action": "specific CTA",
    "image_direction": "visual style/concept for the image",
    "do_not_include": ["anything to avoid"]
  },
  "score_breakdown": {
    "trend_score": 0.85,
    "brand_score": 0.78,
    "risk_score": 0.12,
    "engagement_score": 0.82
  },
  "modifications_required": ["modification 1 if any"],
  "rejection_reason": null,
  "confidence_score": 0.88,
  "message": "one-sentence executive decision statement"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Make the final campaign content decision.

        Context keys expected:
            campaign_title       : str
            campaign_goal        : str
            brand_name           : str
            target_audience      : str
            platforms            : list[str]
            trend_agent_output   : dict
            brand_agent_output   : dict
            risk_agent_output    : dict
            engagement_agent_output : dict
        """
        logger.info("CMOAgent making final decision for: {}", context.get("campaign_title"))

        trend_out    = context.get("trend_agent_output", {})
        brand_out    = context.get("brand_agent_output", {})
        risk_out     = context.get("risk_agent_output", {})
        engage_out   = context.get("engagement_agent_output", {})

        # Extract key scores for hard-gate checks
        risk_score       = float(risk_out.get("risk_score", 0.0))
        brand_score      = float(brand_out.get("brand_alignment_score", 1.0))
        engagement_score = float(engage_out.get("engagement_score", 0.5))
        risk_approved    = risk_out.get("is_approved", True)

        # Hard gate: auto-reject if risk is critical
        if risk_score >= RISK_REJECTION_THRESHOLD or not risk_approved:
            logger.warning(
                "CMOAgent AUTO-REJECT: risk_score={:.0%} exceeds threshold", risk_score
            )
            return AgentResponse(
                agent_name=self.name,
                action=AgentAction.DECIDE,
                message=(
                    f"REJECTED by CMO: Risk score {risk_score:.0%} exceeds safety threshold. "
                    f"Flags: {risk_out.get('risk_flags', [])}"
                ),
                structured_output={
                    "decision": "rejected",
                    "rejection_reason": f"Risk score {risk_score:.0%} exceeds threshold of {RISK_REJECTION_THRESHOLD:.0%}",
                    "risk_flags": risk_out.get("risk_flags", []),
                },
                confidence_score=0.99,
                risk_score=risk_score,
                engagement_score=engagement_score,
            )

        prompt = f"""You are the CMO. Review all agent reports and make your final decision.

Campaign: {context.get('campaign_title', 'N/A')}
Goal: {context.get('campaign_goal', 'brand_awareness')}
Brand: {context.get('brand_name', 'Unknown')}
Target Audience: {context.get('target_audience', 'General')}
Platforms: {', '.join(context.get('platforms', ['instagram', 'twitter']))}

--- TREND AGENT REPORT ---
Primary Trend: {trend_out.get('primary_trend', 'N/A')}
Proposed Angle: {trend_out.get('proposed_angle', 'N/A')}
Confidence: {trend_out.get('confidence_score', 'N/A')}
Hashtags: {', '.join(trend_out.get('hashtags', []))}

--- BRAND AGENT REPORT ---
Alignment Score: {brand_out.get('brand_alignment_score', 'N/A')}
Action Taken: {brand_out.get('action', 'N/A')}
Revised Angle: {brand_out.get('revised_angle', 'None - original angle approved')}
Concerns: {brand_out.get('concerns', [])}

--- RISK AGENT REPORT ---
Risk Score: {risk_score:.0%}
Verdict: {risk_out.get('verdict', 'N/A')}
Risk Flags: {risk_out.get('risk_flags', [])}
Required Modifications: {risk_out.get('required_modifications', [])}

--- ENGAGEMENT AGENT REPORT ---
Engagement Score: {engagement_score:.0%}
Virality Potential: {engage_out.get('virality_potential', 'N/A')}
Hook Suggestions: {engage_out.get('hook_suggestions', [])}
CTA Suggestion: {engage_out.get('call_to_action_suggestion', 'N/A')}
Optimizations: {engage_out.get('content_optimizations', [])}

Make your final executive decision. Synthesize all inputs into a content brief.
Respond with JSON only."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.5)

            decision     = result.get("decision", "approved_modified")
            composite    = float(result.get("composite_score", 0.7))
            confidence   = float(result.get("confidence_score", 0.85))
            message      = result.get("message", f"CMO Decision: {decision.upper()}")

            # Map decision to action
            action_map = {
                "approved":          AgentAction.DECIDE,
                "approved_modified": AgentAction.DECIDE,
                "rejected":          AgentAction.DECIDE,
            }
            action = action_map.get(decision, AgentAction.DECIDE)

            logger.info(
                "CMOAgent final decision: {} | composite_score={:.0%}",
                decision.upper(), composite
            )

            return AgentResponse(
                agent_name=self.name,
                action=action,
                message=message,
                structured_output=result,
                confidence_score=confidence,
                risk_score=risk_score,
                engagement_score=engagement_score,
            )

        except Exception as e:
            return self._error_response(AgentAction.DECIDE, e)
