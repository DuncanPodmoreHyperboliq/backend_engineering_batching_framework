"""
Core data models for the Reliable Imports framework.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID


class BatchStatus(str, Enum):
    """Status values for import batches."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPROCESSING = "reprocessing"


class ItemStatus(str, Enum):
    """Status values for individual batch items."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ImportBatch:
    """
    Represents an import batch operation.

    This is the primary unit of work in the framework. Each batch can contain
    multiple items and can be reprocessed independently.
    """
    id: UUID
    batch_type: str
    status: BatchStatus
    source_info: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    retry_count: int = 0
    parent_batch_id: Optional[UUID] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_complete(self) -> bool:
        """Check if batch has finished processing."""
        return self.status in (BatchStatus.COMPLETED, BatchStatus.FAILED)

    def is_successful(self) -> bool:
        """Check if batch completed successfully."""
        return self.status == BatchStatus.COMPLETED

    def is_reprocess(self) -> bool:
        """Check if this is a reprocessing batch."""
        return self.parent_batch_id is not None


@dataclass
class ImportBatchItem:
    """
    Represents a single item within an import batch.

    Each item maintains its original source data, enabling reliable reprocessing
    without needing to go back to the original data source.
    """
    id: UUID
    batch_id: UUID
    item_index: int
    status: ItemStatus
    source_data: Dict[str, Any]
    processed_data: Optional[Dict[str, Any]] = None
    target_table: Optional[str] = None
    target_id: Optional[UUID] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def is_complete(self) -> bool:
        """Check if item has finished processing."""
        return self.status in (ItemStatus.COMPLETED, ItemStatus.FAILED, ItemStatus.SKIPPED)

    def is_successful(self) -> bool:
        """Check if item completed successfully."""
        return self.status == ItemStatus.COMPLETED


@dataclass
class ImportLog:
    """Represents a log entry for an import operation."""
    id: int
    batch_id: UUID
    item_id: Optional[UUID]
    log_level: str
    message: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BatchSummary:
    """Summary statistics for a batch operation."""
    id: UUID
    batch_type: str
    status: BatchStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    retry_count: int
    total_items: int
    completed_items: int
    failed_items: int
    pending_items: int
    duration_seconds: Optional[float]

    @property
    def success_rate(self) -> float:
        """Calculate the success rate as a percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100

    @property
    def items_per_second(self) -> Optional[float]:
        """Calculate processing throughput."""
        if self.duration_seconds and self.duration_seconds > 0:
            return self.total_items / self.duration_seconds
        return None
