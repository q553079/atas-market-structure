from __future__ import annotations

from atas_market_structure.app_routes._analysis_routes import handle_analysis_routes
from atas_market_structure.app_routes._chat_routes import handle_chat_routes
from atas_market_structure.app_routes._health_routes import handle_health_routes
from atas_market_structure.app_routes._ingestion_routes import handle_ingestion_routes
from atas_market_structure.app_routes._options_routes import handle_options_routes
from atas_market_structure.app_routes._review_routes import handle_review_routes
from atas_market_structure.app_routes._tuning_routes import handle_tuning_routes
from atas_market_structure.app_routes._workbench_routes import handle_workbench_routes

__all__ = [
    "handle_analysis_routes",
    "handle_chat_routes",
    "handle_health_routes",
    "handle_ingestion_routes",
    "handle_options_routes",
    "handle_review_routes",
    "handle_tuning_routes",
    "handle_workbench_routes",
]
