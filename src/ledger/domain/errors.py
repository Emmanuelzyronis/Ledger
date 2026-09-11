"""Domain errors raised when a value or state transition violates LEDGER contracts."""


class DomainError(ValueError):
    """Base class for domain validation failures."""


class InvalidValueError(DomainError):
    """Raised when a domain value cannot satisfy its contract."""


class InvalidTransitionError(DomainError):
    """Raised when a state-machine transition is not permitted."""
