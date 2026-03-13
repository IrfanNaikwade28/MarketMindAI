"""
app/agents/trend_agent.py
--------------------------
TrendAgent — the first speaker in every debate.

Role:
  Analyzes current social media trends relevant to the campaign topic
  and proposes a content angle that rides the trend wave.

Output:
  - Identified trend(s)
  - Viral potential score
  - Proposed content angle
  - Recommended hashtags
  - Platform-specific trend notes
"""

from typing import Any

from loguru import logger

from app.agents.base_agent import BaseAgent, AgentResponse
from app.models.agent_log import AgentName, AgentAction


class TrendAgent(BaseAgent):
    name = AgentName.TREND
    system_prompt = """You are the Trend Agent in an AI marketing council.

Your sole responsibility is to identify and analyze current social media trends
that are relevant to the given campaign topic, brand, and target audience.

You think like a viral content strategist who lives on social media 24/7.
You know what's trending on Instagram Reels, Twitter/X, YouTube Shorts, TikTok,
and LinkedIn at any given moment.

When given a campaign brief, you must:
1. Identify 2-3 relevant trends currently dominating social media
2. Score each trend's viral potential (0.0 to 1.0)
3. Propose a specific content angle that rides the strongest trend
4. Suggest platform-specific adaptations of the trend
5. Recommend 5-10 hashtags with estimated reach

IMPORTANT: You must respond with ONLY valid JSON in this exact structure:
{
  "trends": [
    {
      "name": "trend name",
      "description": "brief description of the trend",
      "viral_potential": 0.85,
      "platforms": ["instagram", "twitter", "youtube"],
      "estimated_reach": "2.3M"
    }
  ],
  "proposed_angle": "specific content angle that leverages the top trend",
  "primary_trend": "name of the strongest trend to ride",
  "hashtags": ["#hashtag1", "#hashtag2"],
  "platform_notes": {
    "instagram": "reel format, trending audio suggestion",
    "twitter": "thread or single post approach",
    "youtube": "title hook suggestion"
  },
  "confidence_score": 0.87,
  "reasoning": "brief explanation of why this trend fits the campaign"
}"""

    async def run(
        self,
        context: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> AgentResponse:
        """
        Analyze trends and propose a content angle.

        Context keys expected:
            campaign_title    : str
            campaign_goal     : str
            target_audience   : str
            brand_name        : str
            keywords          : list[str]
            platforms         : list[str]
        """
        logger.info("TrendAgent running for campaign: {}", context.get("campaign_title"))

        prompt = f"""Analyze social media trends for this campaign and propose the best content angle.

Campaign Title: {context.get('campaign_title', 'N/A')}
Campaign Goal: {context.get('campaign_goal', 'brand_awareness')}
Target Audience: {context.get('target_audience', 'General audience')}
Brand Name: {context.get('brand_name', 'Unknown Brand')}
Keywords: {', '.join(context.get('keywords', []))}
Target Platforms: {', '.join(context.get('platforms', ['instagram', 'twitter']))}

Identify the most relevant current trends and propose a compelling content angle.
Respond with JSON only."""

        try:
            result = await self._chat(user_prompt=prompt, history=history, temperature=0.8)

            trends = result.get("trends", [])
            top_trend = trends[0] if trends else {}
            confidence = float(result.get("confidence_score", 0.75))

            message = (
                f"Trend detected: '{result.get('primary_trend', 'Unknown')}' "
                f"with {top_trend.get('estimated_reach', 'N/A')} estimated reach. "
                f"Proposed angle: {result.get('proposed_angle', '')[:100]}..."
            )

            logger.info("TrendAgent complete | confidence={:.0%}", confidence)

            return AgentResponse(
                agent_name=self.name,
                action=AgentAction.PROPOSE,
                message=message,
                structured_output=result,
                confidence_score=confidence,
                risk_score=0.1,  # Trend Agent defaults low risk — Risk Agent will assess
                engagement_score=float(top_trend.get("viral_potential", 0.7)),
            )

        except Exception as e:
            return self._error_response(AgentAction.PROPOSE, e)
