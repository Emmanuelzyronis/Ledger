"""LEDGER package with foundation and infrastructure-independent domain modules."""

__version__ = "0.1.0"
from .ingestion import IngestionResult, IngestionService, RawIngestion, canonical_payload, content_fingerprint
from .validation import Validation, ValidationService
from .normalization import Normalization, NormalizationService
from .identity import Identity, IdentityService, TransactionIdentity, canonical_fingerprint, canonical_identity, source_identity
from .candidates import CandidateGeneration, CandidateGenerationService, CandidateGenerator
from .matching import MatchDecision, Matching, MatchingService
from .reconciliation import ReconciliationEngine, ReconciliationService
from .resolution import ResolutionEngine, ResolutionResult, ResolutionService
from .api import APIError, LedgerAPI, create_app
from .reporting import ReportingService
from .service import LedgerASGI, LedgerService, ServiceSettings, create_app as create_service_app
from .security import HmacTokenVerifier, Principal, RateLimiter, SecurityPolicy, StaticTokenVerifier

__all__ = ["APIError", "CandidateGeneration", "CandidateGenerationService", "CandidateGenerator", "Identity", "IdentityService", "IngestionResult", "IngestionService", "LedgerAPI", "MatchDecision", "Matching", "MatchingService", "Normalization", "NormalizationService", "RawIngestion", "ReconciliationEngine", "ReconciliationService", "ResolutionEngine", "ResolutionResult", "ResolutionService", "HmacTokenVerifier", "LedgerASGI", "LedgerService", "Principal", "RateLimiter", "ReportingService", "SecurityPolicy", "ServiceSettings", "StaticTokenVerifier", "TransactionIdentity", "Validation", "ValidationService", "canonical_fingerprint", "canonical_identity", "canonical_payload", "content_fingerprint", "create_app", "create_service_app", "source_identity"]
