"""Grounded learning-content and narration services for DiSan Lens.

The package is intentionally independent from the FastAPI wiring.  Callers can
inject the services into an application without changing the canonical
heritage repository or the recognition pipeline.
"""

from .cache import AudioFileCache, SQLiteLearningContentCache
from .evidence import EvidenceValidationError, build_evidence_catalog
from .providers import (
    OpenAIResponsesProvider,
    OpenAISpeechProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderUnavailableError,
)
from .schemas import (
    LearningContentEnvelope,
    NarrationRequest,
    NarrationResponse,
    GeneratedLearningContent,
)
from .service import (
    ArtifactNotFoundError,
    LearningService,
    NarrationService,
    build_ai_services,
)

__all__ = [
    "ArtifactNotFoundError",
    "AudioFileCache",
    "EvidenceValidationError",
    "GeneratedLearningContent",
    "LearningContentEnvelope",
    "LearningService",
    "NarrationRequest",
    "NarrationResponse",
    "NarrationService",
    "OpenAIResponsesProvider",
    "OpenAISpeechProvider",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderInvalidResponseError",
    "ProviderUnavailableError",
    "SQLiteLearningContentCache",
    "build_ai_services",
    "build_evidence_catalog",
]
