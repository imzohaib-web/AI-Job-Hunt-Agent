"""
backend/services/analytics_service.py
-------------------------------------
Dashboard metrics from Agents.analytics.compute_dashboard_metrics.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.exceptions import AgentProcessingError

logger = logging.getLogger("job_agent.api.analytics")


class AnalyticsService:
    """Read-only analytics from SQLite via the analytics agent."""

    async def get_summary(self, profile_id: Optional[int] = None) -> Dict[str, Any]:
        from Agents.analytics import compute_dashboard_metrics

        logger.info("Fetching analytics (profile_id=%s)", profile_id)
        try:
            metrics = await asyncio.to_thread(compute_dashboard_metrics, profile_id)
            return metrics
        except Exception as e:
            logger.exception("Analytics failed")
            raise AgentProcessingError(f"Analytics failed: {e}") from e
