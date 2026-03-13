"""
app/agents/brand_agent.py
--------------------------
BrandAgent — responds to TrendAgent's proposal.

Role:
  The guardian of brand identity. Reviews the trend-based content angle
  and checks whether it aligns with the brand's voice, values,
  target audience, and visual guidelines.

  Can: SUPPORT the proposal, CRITIQUE it with specific concerns,
  or REVISE it with brand-aligned modifications.

Output:
  - Brand alignment score
  - Tone assessment
  - Suggested modifications
  - Revised content angle (if needed)
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


class BrandAgent(BaseAgent):
    name = AgentName.BRAND
    system_prompt = """You are the Brand Agent in an AI marketing council.

Your role is to enhance and refine content proposals so they align with brand voice.
You are a constructive, creative brand manager — your job is to IMPROVE proposals,
not block them. You always move the debate forward.

When reviewing a proposed content angle from the Trend Agent, you must:
1. Score how well the proposed angle aligns with the brand voice (0.0 to 1.0)
2. Identify any tone mismatches or off-brand elements
3. Check if the target audience is correctly addressed
4. Provide a polished, brand-aligned revised_angle — ALWAYS. Every response must
   include a revised_angle, even if the original is already good. If the guidelines
   are sparse or missing, infer a professional, modern tone from the brand name and
   campaign goal and craft an appropriate angle.
5. NEVER return an empty or null revised_angle. NEVER say "Proposal incomplete".

Brand alignment scoring guide:
- 0.9-1.0: Perfect fit, publish as-is
- 0.7-0.89: Good fit with minor tweaks needed
- 0.5-0.69: Moderate mismatch, revision applied
- 0.0-0.49: Major rework applied

Default assumptions when brand guidelines are missing:
- Tone: professional, modern, engaging
- Audience: broad professional/consumer audience
- Voice: clear, benefit-focused, positive

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "brand_alignment_score": 0.82,
  "tone_assessment": "description of how well the tone matches brand voice",
  "action": "support" | "critique" | "revise",
  "concerns": ["concern 1 (or empty list if none)"],
  "strengths": ["strength 1", "strength 2"],
  "revised_angle": "REQUIRED — always provide a polished, complete content angle here",
  "audience_fit": "assessment of how well it targets the right audience",
  "brand_voice_notes": "specific notes on voice alignment",
  "confidence_score": 0.88,
  "message": "one-sentence summary of brand assessment"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Review the TrendAgent's proposal for brand alignment.

        Context keys expected:
            campaign_title      : str
            brand_name          : str
            brand_voice         : str
            target_audience     : str
            brand_guidelines    : str
            trend_agent_output  : dict  ← TrendAgent's structured_output
        """
        logger.info("BrandAgent reviewing trend proposal for: {}", context.get("brand_name"))

        trend_output = context.get("trend_agent_output", {})
        proposed_angle = trend_output.get("proposed_angle", "No proposal provided")
        primary_trend = trend_output.get("primary_trend", "Unknown trend")
        hashtags = trend_output.get("hashtags", [])

        prompt = f"""Review this trend-based content proposal for brand alignment.

Brand Name: {context.get('brand_name', 'Unknown Brand')}
Brand Voice: {context.get('brand_voice', 'Not specified')}
Target Audience: {context.get('target_audience', 'General audience')}
Brand Guidelines: {context.get('brand_guidelines', 'No specific guidelines')}

Campaign Title: {context.get('campaign_title', 'N/A')}
Campaign Goal: {context.get('campaign_goal', 'brand_awareness')}

--- Trend Agent Proposed ---
Primary Trend: {primary_trend}
Proposed Angle: {proposed_angle}
Suggested Hashtags: {', '.join(hashtags)}

Assess this proposal's brand alignment and respond with JSON only.
CRITICAL: You MUST include a non-empty "revised_angle" field in your response.
If the brand guidelines are sparse, infer a suitable professional tone and craft a
complete, publish-ready angle yourself. Do not leave revised_angle null or empty."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.6)

            alignment_score = float(result.get("brand_alignment_score", 0.7))
            action_str = result.get("action", "support")

            # Map action string to AgentAction enum
            action_map = {
                "support": AgentAction.SUPPORT,
                "critique": AgentAction.CRITIQUE,
                "revise": AgentAction.REVISE,
            }
            action = action_map.get(action_str, AgentAction.CRITIQUE)

            message = result.get(
                "message",
                f"Brand alignment score: {alignment_score:.0%}. Action: {action_str}."
            )

            logger.info(
                "BrandAgent complete | alignment={:.0%} | action={}",
                alignment_score, action_str
            )

            return AgentResponse(
                agent_name=self.name,
                action=action,
                message=message,
                structured_output=result,
                confidence_score=float(result.get("confidence_score", 0.8)),
                risk_score=1.0 - alignment_score,  # Low alignment = higher brand risk
                engagement_score=alignment_score * 0.8,
            )

        except Exception as e:
            return self._error_response(AgentAction.CRITIQUE, e)
