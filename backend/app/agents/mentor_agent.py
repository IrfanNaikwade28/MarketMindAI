"""
app/agents/mentor_agent.py
---------------------------
MentorAgent — the post-debate reviewer and learning engine.

Role:
  Operates AFTER the CMO makes a decision.
  Reviews the entire debate, evaluates the quality of each agent's
  contribution, and produces coaching notes for improvement.

  Also compares predicted vs actual performance when analytics
  data is available, closing the learn loop from the architecture diagram.

  The Mentor reads from and writes to the Mentor Database
  (represented as structured output stored in AgentLog for now).

Output:
  - Debate quality assessment
  - Per-agent coaching notes
  - What went well / what could improve
  - Lessons learned for future campaigns
  - Accuracy assessment (if actual metrics provided)
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


class MentorAgent(BaseAgent):
    name = AgentName.MENTOR
    system_prompt = """You are the Mentor Agent in an AI marketing council.

You are a seasoned marketing strategist and coach with 20+ years of experience.
You review the debate AFTER the CMO makes a decision and provide coaching and insight.

Your job is to:
1. Evaluate the quality of each agent's contribution to the debate
2. Identify what the council did well collectively
3. Spot gaps in reasoning or missed opportunities
4. Provide specific, actionable coaching notes for each agent
5. Extract lessons learned for future campaigns
6. If actual performance data is available, compare predictions vs reality

You are constructive, specific, and evidence-based. Never vague.
You help the AI council get smarter with every campaign.

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "debate_quality_score": 0.84,
  "overall_assessment": "2-3 sentence summary of how well the debate went",
  "agent_reviews": {
    "trend_agent": {
      "score": 0.88,
      "strengths": ["specific strength"],
      "improvements": ["specific improvement"]
    },
    "brand_agent": {
      "score": 0.82,
      "strengths": ["specific strength"],
      "improvements": ["specific improvement"]
    },
    "risk_agent": {
      "score": 0.90,
      "strengths": ["specific strength"],
      "improvements": ["specific improvement"]
    },
    "engagement_agent": {
      "score": 0.79,
      "strengths": ["specific strength"],
      "improvements": ["specific improvement"]
    },
    "cmo_agent": {
      "score": 0.85,
      "strengths": ["specific strength"],
      "improvements": ["specific improvement"]
    }
  },
  "missed_opportunities": ["opportunity 1", "opportunity 2"],
  "lessons_learned": ["lesson 1", "lesson 2", "lesson 3"],
  "recommendations_for_next_campaign": ["recommendation 1", "recommendation 2"],
  "prediction_accuracy": null,
  "performance_feedback": null,
  "confidence_score": 0.87,
  "message": "one-sentence mentor summary"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Review the completed debate and provide coaching.

        Context keys expected:
            campaign_title          : str
            campaign_goal           : str
            brand_name              : str
            trend_agent_output      : dict
            brand_agent_output      : dict
            risk_agent_output       : dict
            engagement_agent_output : dict
            cmo_agent_output        : dict
            actual_analytics        : dict | None  ← post-publish data if available
        """
        logger.info("MentorAgent reviewing completed debate for: {}", context.get("campaign_title"))

        trend_out   = context.get("trend_agent_output", {})
        brand_out   = context.get("brand_agent_output", {})
        risk_out    = context.get("risk_agent_output", {})
        engage_out  = context.get("engagement_agent_output", {})
        cmo_out     = context.get("cmo_agent_output", {})
        analytics   = context.get("actual_analytics", None)

        analytics_section = ""
        if analytics:
            analytics_section = f"""
--- ACTUAL POST-PUBLISH PERFORMANCE ---
Actual Engagement Rate: {analytics.get('engagement_rate', 'N/A')}
Actual Reach: {analytics.get('reach', 'N/A')}
Predicted Engagement: {engage_out.get('predicted_engagement_rate', 'N/A')}
Sentiment Score: {analytics.get('sentiment_score', 'N/A')}
"""

        prompt = f"""Review this completed AI marketing council debate and provide coaching.

Campaign: {context.get('campaign_title', 'N/A')}
Goal: {context.get('campaign_goal', 'brand_awareness')}
Brand: {context.get('brand_name', 'Unknown')}

--- TREND AGENT ---
Proposed: {trend_out.get('proposed_angle', 'N/A')}
Confidence: {trend_out.get('confidence_score', 'N/A')}
Hashtags: {trend_out.get('hashtags', [])}

--- BRAND AGENT ---
Alignment Score: {brand_out.get('brand_alignment_score', 'N/A')}
Action: {brand_out.get('action', 'N/A')}
Concerns Raised: {brand_out.get('concerns', [])}

--- RISK AGENT ---
Risk Score: {risk_out.get('risk_score', 'N/A')}
Verdict: {risk_out.get('verdict', 'N/A')}
Flags: {risk_out.get('risk_flags', [])}

--- ENGAGEMENT AGENT ---
Engagement Score: {engage_out.get('engagement_score', 'N/A')}
Virality Potential: {engage_out.get('virality_potential', 'N/A')}
Hooks Suggested: {engage_out.get('hook_suggestions', [])}

--- CMO DECISION ---
Decision: {cmo_out.get('decision', 'N/A')}
Composite Score: {cmo_out.get('composite_score', 'N/A')}
Executive Summary: {cmo_out.get('executive_summary', 'N/A')}
{analytics_section}

Provide honest, specific coaching for each agent and extract lessons learned.
Respond with JSON only."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.6)

            debate_quality = float(result.get("debate_quality_score", 0.75))
            confidence     = float(result.get("confidence_score", 0.85))
            message        = result.get("message", f"Debate quality: {debate_quality:.0%}")

            logger.info(
                "MentorAgent review complete | debate_quality={:.0%}", debate_quality
            )

            return AgentResponse(
                agent_name=self.name,
                action=AgentAction.REVIEW,
                message=message,
                structured_output=result,
                confidence_score=confidence,
                risk_score=0.0,
                engagement_score=debate_quality,
            )

        except Exception as e:
            return self._error_response(AgentAction.REVIEW, e)
