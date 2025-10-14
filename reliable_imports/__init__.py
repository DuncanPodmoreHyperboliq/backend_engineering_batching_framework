"""
Reliable Imports Framework

A convention-based Python framework for reliable data ingestion with PostgreSQL.
Designed to save developer time through batch processing, import IDs, and easy reprocessing.
"""

from .models import ImportBatch, ImportBatchItem, BatchStatus, ItemStatus
from .batch import BatchManager
from .processor import BaseProcessor
from .context import ImportContext
from .registry import ProcessorRegistry, processor
from .exceptions import (
    ImportError,
    BatchNotFoundError,
    ProcessorNotFoundError,
    ValidationError,
)

__version__ = "1.0.0"
__all__ = [
    # Core classes
    "ImportBatch",
    "ImportBatchItem",
    "BatchManager",
    "BaseProcessor",
    "ImportContext",
    "ProcessorRegistry",
    # Enums
    "BatchStatus",
    "ItemStatus",
    # Decorators
    "processor",
    # Exceptions
    "ImportError",
    "BatchNotFoundError",
    "ProcessorNotFoundError",
    "ValidationError",
]
