"""
app/agents/risk_agent.py
-------------------------
RiskAgent — the safety watchdog of the council.

Role:
  Evaluates the proposed content for legal, reputational,
  cultural sensitivity, and platform policy risks.
  Issues WARN actions for flagged content, SUPPORT for safe content.

  A high risk score can veto the debate entirely —
  the CMO Agent uses this score as a hard gate.

Output:
  - Overall risk score
  - Specific risk flags by category
  - Safe / Unsafe verdict
  - Recommended modifications to mitigate risks
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


class RiskAgent(BaseAgent):
    name = AgentName.RISK
    system_prompt = """You are the Risk Agent in an AI marketing council.

Your role is to protect the brand from GENUINE, CONCRETE risks — not hypothetical ones.
You are a pragmatic safety officer, not a creative blocker.

You look for:
- Legal issues (copyright, defamation, false claims, regulated industries)
- Reputational damage (controversial topics, offensive language, insensitive content)
- Platform policy violations (concrete violations, not vague concerns)
- Cultural insensitivity (stereotypes, appropriation, exclusion)

IMPORTANT CALIBRATION — these are NOT risks and should NOT be flagged:
- Standard B2B/B2C SaaS or AI product marketing
- Generic productivity or tech-industry content angles
- Professional or motivational messaging without controversial claims
- Content that is merely "generic" or "unclear" — that is a Brand concern, not a Risk
- Vague or incomplete briefs — evaluate what IS there, don't penalise for what's missing

When content is standard marketing for a legitimate product, your risk_score should be
LOW (0.0–0.3) and is_approved should be TRUE. Reserve high scores (0.7+) for content
with SPECIFIC, NAMED violations (e.g., an illegal health claim, a copied trademark).

Risk scoring guide:
- 0.0-0.2: Safe — approve without changes (default for normal marketing)
- 0.2-0.4: Low risk — minor suggestions only, still approved
- 0.4-0.6: Medium risk — modifications required, conditionally approved
- 0.6-0.8: High risk — major revision needed, not approved
- 0.8-1.0: Critical risk — concrete severe violation, recommend rejection

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "risk_score": 0.15,
  "verdict": "safe" | "low_risk" | "medium_risk" | "high_risk" | "critical",
  "is_approved": true,
  "risk_flags": [
    {
      "category": "legal" | "reputational" | "platform_policy" | "cultural" | "crisis",
      "severity": "low" | "medium" | "high",
      "description": "specific, concrete risk description",
      "mitigation": "how to fix this"
    }
  ],
  "platform_violations": {
    "instagram": null,
    "twitter": null,
    "youtube": null
  },
  "safe_elements": ["element 1 that is safe", "element 2"],
  "required_modifications": ["modification 1 if any — leave empty list if none needed"],
  "confidence_score": 0.92,
  "message": "one-sentence risk verdict summary"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Evaluate the content proposal for risks.

        Context keys expected:
            campaign_title      : str
            brand_name          : str
            target_audience     : str
            platforms           : list[str]
            trend_agent_output  : dict
            brand_agent_output  : dict
        """
        logger.info("RiskAgent evaluating content for: {}", context.get("brand_name"))

        trend_output = context.get("trend_agent_output", {})
        brand_output = context.get("brand_agent_output", {})

        # Use brand agent revised angle if available, else trend proposed angle
        final_angle = (
            brand_output.get("revised_angle")
            or trend_output.get("proposed_angle", "No angle provided")
        )
        hashtags = trend_output.get("hashtags", [])
        primary_trend = trend_output.get("primary_trend", "Unknown")

        prompt = f"""Evaluate this social media content proposal for potential risks.

Brand: {context.get('brand_name', 'Unknown')}
Target Audience: {context.get('target_audience', 'General audience')}
Platforms: {', '.join(context.get('platforms', ['instagram', 'twitter']))}
Campaign Goal: {context.get('campaign_goal', 'brand_awareness')}

--- Content to Evaluate ---
Primary Trend Being Used: {primary_trend}
Final Content Angle: {final_angle}
Hashtags: {', '.join(hashtags)}
Brand Alignment Score: {brand_output.get('brand_alignment_score', 'N/A')}

Identify all CONCRETE risks, rate their severity, and give a final verdict.
For standard AI/tech/SaaS marketing content with no specific violations, default to
risk_score <= 0.25 and is_approved: true. Only escalate if you can name a specific,
real violation. Respond with JSON only."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.4)

            risk_score = float(result.get("risk_score", 0.2))
            is_approved = result.get("is_approved", True)
            verdict = result.get("verdict", "safe")

            # Risk Agent WARNs if any flags exist, else SUPPORTs
            flags = result.get("risk_flags", [])
            action = AgentAction.WARN if flags else AgentAction.SUPPORT

            message = result.get(
                "message",
                f"Risk verdict: {verdict.upper()}. Score: {risk_score:.0%}. "
                f"{'Approved.' if is_approved else 'Requires revision.'}"
            )

            logger.info(
                "RiskAgent complete | verdict={} | risk={:.0%} | approved={}",
                verdict, risk_score, is_approved
            )

            return AgentResponse(
                agent_name=self.name,
                action=action,
                message=message,
                structured_output=result,
                confidence_score=float(result.get("confidence_score", 0.85)),
                risk_score=risk_score,
                engagement_score=max(0.0, 1.0 - risk_score),
            )

        except Exception as e:
            return self._error_response(AgentAction.WARN, e)
