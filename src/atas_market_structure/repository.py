from __future__ import annotations

# compatibility facade only; do not add new business logic here

from atas_market_structure.repository_chat import ChatRepository
from atas_market_structure.repository_evaluation_tuning import EvaluationTuningRepository
from atas_market_structure.repository_projection import ProjectionRepository
from atas_market_structure.repository_protocols import AnalysisRepository, ChartCandleRepository, IngestionRepository
from atas_market_structure.repository_raw_ingestion import RawIngestionRepository
from atas_market_structure.repository_recognition import RecognitionRepository
from atas_market_structure.repository_records import (
    StoredAnalysis,
    StoredBeliefState,
    StoredChatAnnotation,
    StoredChatMessage,
    StoredChatPlanCard,
    StoredChatSession,
    StoredEpisodeEvaluation,
    StoredEventEpisode,
    StoredEventCandidate,
    StoredEventMemoryEntry,
    StoredEventOutcomeLedger,
    StoredEventStreamEntry,
    StoredIngestion,
    StoredIngestionDeadLetter,
    StoredIngestionIdempotencyKey,
    StoredIngestionRunLog,
    StoredInstrumentProfile,
    StoredLiquidityMemory,
    StoredPatchPromotionHistoryRecord,
    StoredPatchValidationResultRecord,
    StoredPipelineContractOverview,
    StoredPipelineDailyCount,
    StoredProfilePatchCandidateRecord,
    StoredPromptBlock,
    StoredPromptTrace,
    StoredRecognizerBuild,
    StoredSessionMemory,
    StoredTuningRecommendationRecord,
)
from atas_market_structure.repository_sqlite import SQLiteAnalysisRepository

__all__ = [
    "AnalysisRepository",
    "ChartCandleRepository",
    "ChatRepository",
    "EvaluationTuningRepository",
    "IngestionRepository",
    "ProjectionRepository",
    "RawIngestionRepository",
    "RecognitionRepository",
    "SQLiteAnalysisRepository",
    "StoredAnalysis",
    "StoredBeliefState",
    "StoredChatAnnotation",
    "StoredChatMessage",
    "StoredChatPlanCard",
    "StoredChatSession",
    "StoredEpisodeEvaluation",
    "StoredEventCandidate",
    "StoredEventEpisode",
    "StoredEventMemoryEntry",
    "StoredEventOutcomeLedger",
    "StoredEventStreamEntry",
    "StoredIngestion",
    "StoredIngestionDeadLetter",
    "StoredIngestionIdempotencyKey",
    "StoredIngestionRunLog",
    "StoredInstrumentProfile",
    "StoredLiquidityMemory",
    "StoredPatchPromotionHistoryRecord",
    "StoredPatchValidationResultRecord",
    "StoredPipelineContractOverview",
    "StoredPipelineDailyCount",
    "StoredProfilePatchCandidateRecord",
    "StoredPromptBlock",
    "StoredPromptTrace",
    "StoredRecognizerBuild",
    "StoredSessionMemory",
    "StoredTuningRecommendationRecord",
]
