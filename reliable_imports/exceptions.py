"""
Custom exceptions for the Reliable Imports framework.
"""


class ImportError(Exception):
    """Base exception for all import-related errors."""
    pass


class BatchNotFoundError(ImportError):
    """Raised when a requested batch cannot be found."""
    pass


class ProcessorNotFoundError(ImportError):
    """Raised when a processor for a batch type is not registered."""
    pass


class ValidationError(ImportError):
    """Raised when data validation fails."""
    pass


class ProcessingError(ImportError):
    """Raised when processing fails for a batch or item."""
    pass


class ConfigurationError(ImportError):
    """Raised when framework configuration is invalid."""
    pass
