"""
app/agents/engagement_agent.py
-------------------------------
EngagementAgent — the audience psychology expert.

Role:
  Predicts how the target audience will respond to the proposed content.
  Uses psychology, platform algorithm knowledge, and content performance
  patterns to score engagement potential and suggest optimizations.

Output:
  - Predicted engagement rate
  - Virality potential
  - Platform-specific performance predictions
  - Emotional trigger analysis
  - Optimal posting time recommendations
  - Hook suggestions
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


class EngagementAgent(BaseAgent):
    name = AgentName.ENGAGEMENT
    system_prompt = """You are the Engagement Agent in an AI marketing council.

Your expertise is audience psychology, content performance, and platform algorithms.
You predict how content will perform before it's published and suggest optimizations
to maximize authentic engagement (not vanity metrics).

You understand:
- What makes people stop scrolling (pattern interrupts, emotional hooks)
- Platform-specific algorithm factors (Instagram Reels boost, Twitter/X thread engagement)
- Optimal content formats for each platform
- Psychological triggers that drive comments, shares, and saves
- Time-of-day and day-of-week posting patterns
- How trends amplify organic reach

Engagement score guide:
- 0.9-1.0: Viral potential — exceptional engagement expected
- 0.7-0.89: High engagement — strong performance expected
- 0.5-0.69: Moderate engagement — average performance
- 0.3-0.49: Low engagement — needs improvement
- 0.0-0.29: Poor — likely to underperform

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "predicted_engagement_rate": 0.078,
  "engagement_score": 0.82,
  "virality_potential": 0.65,
  "emotional_triggers": ["curiosity", "inspiration", "FOMO"],
  "platform_predictions": {
    "instagram": {
      "estimated_reach": "45K-120K",
      "predicted_likes": "2.1K-5.8K",
      "predicted_comments": "180-450",
      "predicted_shares": "320-890",
      "algorithm_boost_likelihood": "high"
    },
    "twitter": {
      "estimated_impressions": "12K-35K",
      "predicted_retweets": "85-240",
      "predicted_replies": "45-130"
    },
    "youtube": {
      "predicted_ctr": "6.2%",
      "estimated_views": "8K-22K"
    }
  },
  "hook_suggestions": ["hook option 1", "hook option 2", "hook option 3"],
  "optimal_posting_times": {
    "instagram": "Tuesday-Thursday 11am-1pm or 7pm-9pm EST",
    "twitter": "Weekdays 9am-10am EST",
    "youtube": "Thursday-Friday 3pm-5pm EST"
  },
  "content_optimizations": ["optimization suggestion 1", "suggestion 2"],
  "call_to_action_suggestion": "specific CTA that will drive action",
  "confidence_score": 0.79,
  "message": "one-sentence engagement prediction summary"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Predict engagement and suggest content optimizations.

        Context keys expected:
            campaign_title      : str
            campaign_goal       : str
            target_audience     : str
            platforms           : list[str]
            brand_name          : str
            trend_agent_output  : dict
            brand_agent_output  : dict
            risk_agent_output   : dict
        """
        logger.info("EngagementAgent predicting engagement for: {}", context.get("campaign_title"))

        trend_output = context.get("trend_agent_output", {})
        brand_output = context.get("brand_agent_output", {})
        risk_output  = context.get("risk_agent_output", {})

        # Use the most refined version of the content angle so far
        final_angle = (
            brand_output.get("revised_angle")
            or trend_output.get("proposed_angle", "No angle provided")
        )
        primary_trend = trend_output.get("primary_trend", "Unknown")
        hashtags = trend_output.get("hashtags", [])
        brand_alignment = brand_output.get("brand_alignment_score", "N/A")
        risk_score = risk_output.get("risk_score", 0.0)
        is_approved_by_risk = risk_output.get("is_approved", True)

        prompt = f"""Predict the engagement performance of this social media content proposal.

Campaign: {context.get('campaign_title', 'N/A')}
Campaign Goal: {context.get('campaign_goal', 'brand_awareness')}
Brand: {context.get('brand_name', 'Unknown')}
Target Audience: {context.get('target_audience', 'General audience')}
Platforms: {', '.join(context.get('platforms', ['instagram', 'twitter']))}

--- Content Proposal (Post-Review) ---
Trend Being Used: {primary_trend}
Content Angle: {final_angle}
Hashtags: {', '.join(hashtags)}

--- Prior Agent Scores ---
Brand Alignment: {brand_alignment}
Risk Score: {risk_score} ({'Risk-approved' if is_approved_by_risk else 'Risk-flagged'})

Predict engagement rates, suggest hooks, and recommend optimizations.
Respond with JSON only."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.7)

            engagement_score = float(result.get("engagement_score", 0.65))
            virality = float(result.get("virality_potential", 0.5))
            confidence = float(result.get("confidence_score", 0.75))

            message = result.get(
                "message",
                f"Predicted engagement score: {engagement_score:.0%}. "
                f"Virality potential: {virality:.0%}."
            )

            logger.info(
                "EngagementAgent complete | engagement={:.0%} | virality={:.0%}",
                engagement_score, virality
            )

            return AgentResponse(
                agent_name=self.name,
                action=AgentAction.PROPOSE,
                message=message,
                structured_output=result,
                confidence_score=confidence,
                risk_score=float(risk_output.get("risk_score", 0.0)),
                engagement_score=engagement_score,
            )

        except Exception as e:
            return self._error_response(AgentAction.PROPOSE, e)
