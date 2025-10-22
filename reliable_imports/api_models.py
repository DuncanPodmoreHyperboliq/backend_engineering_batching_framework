"""
Pydantic models for REST API request/response validation.

These models provide automatic validation, serialization, and
OpenAPI documentation generation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class CreateBatchRequest(BaseModel):
    """Request model for creating a new batch."""

    batch_type: str = Field(..., description="Type of batch to create")
    items: List[Dict[str, Any]] = Field(..., description="List of items to process")
    source_info: Optional[Dict[str, Any]] = Field(None, description="Metadata about the data source")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional batch metadata")
    auto_process: bool = Field(False, description="Automatically start processing after creation")

    @validator('items')
    def validate_items_not_empty(cls, v):
        if not v:
            raise ValueError("items list cannot be empty")
        return v

    class Config:
        schema_extra = {
            "example": {
                "batch_type": "customer_data",
                "items": [
                    {"email": "john@example.com", "name": "John Doe"},
                    {"email": "jane@example.com", "name": "Jane Smith"}
                ],
                "source_info": {"file": "customers_2024.csv"},
                "auto_process": True
            }
        }


class ProcessBatchRequest(BaseModel):
    """Request model for processing an existing batch."""

    continue_on_error: bool = Field(True, description="Whether to continue processing if an item fails")

    class Config:
        schema_extra = {
            "example": {
                "continue_on_error": True
            }
        }


class ReprocessBatchRequest(BaseModel):
    """Request model for reprocessing a batch."""

    failed_items_only: bool = Field(True, description="Only reprocess items that failed")
    continue_on_error: bool = Field(True, description="Whether to continue processing if an item fails")

    class Config:
        schema_extra = {
            "example": {
                "failed_items_only": True,
                "continue_on_error": True
            }
        }


class BatchItemResponse(BaseModel):
    """Response model for a batch item."""

    id: UUID
    batch_id: UUID
    item_index: int
    status: str
    source_data: Dict[str, Any]
    processed_data: Optional[Dict[str, Any]] = None
    target_table: Optional[str] = None
    target_id: Optional[UUID] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        orm_mode = True


class BatchResponse(BaseModel):
    """Response model for a batch."""

    id: UUID
    batch_type: str
    status: str
    source_info: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    retry_count: int = 0
    parent_batch_id: Optional[UUID] = None

    class Config:
        orm_mode = True


class BatchSummaryResponse(BaseModel):
    """Response model for batch summary statistics."""

    id: UUID
    batch_type: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int
    total_items: int
    completed_items: int
    failed_items: int
    pending_items: int
    duration_seconds: Optional[float] = None
    success_rate: float = Field(..., description="Success rate as a percentage (0-100)")
    items_per_second: Optional[float] = Field(None, description="Processing throughput")

    class Config:
        orm_mode = True


class CreateBatchResponse(BaseModel):
    """Response model for batch creation."""

    batch_id: UUID
    batch_type: str
    total_items: int
    status: str
    message: str = "Batch created successfully"

    class Config:
        schema_extra = {
            "example": {
                "batch_id": "550e8400-e29b-41d4-a716-446655440000",
                "batch_type": "customer_data",
                "total_items": 2,
                "status": "pending",
                "message": "Batch created successfully"
            }
        }


class ProcessBatchResponse(BaseModel):
    """Response model for batch processing."""

    batch_id: UUID
    status: str
    summary: BatchSummaryResponse
    message: str = "Batch processing completed"

    class Config:
        schema_extra = {
            "example": {
                "batch_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "completed",
                "message": "Batch processing completed",
                "summary": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "batch_type": "customer_data",
                    "status": "completed",
                    "total_items": 2,
                    "completed_items": 2,
                    "failed_items": 0,
                    "pending_items": 0,
                    "success_rate": 100.0
                }
            }
        }


class ReprocessBatchResponse(BaseModel):
    """Response model for batch reprocessing."""

    original_batch_id: UUID
    new_batch_id: UUID
    items_to_reprocess: int
    status: str
    message: str = "Batch reprocessed successfully"

    class Config:
        schema_extra = {
            "example": {
                "original_batch_id": "550e8400-e29b-41d4-a716-446655440000",
                "new_batch_id": "660e8400-e29b-41d4-a716-446655440001",
                "items_to_reprocess": 5,
                "status": "completed",
                "message": "Batch reprocessed successfully"
            }
        }


class BatchListResponse(BaseModel):
    """Response model for listing batches."""

    batches: List[BatchSummaryResponse]
    total: int
    offset: int
    limit: int

    class Config:
        schema_extra = {
            "example": {
                "batches": [],
                "total": 10,
                "offset": 0,
                "limit": 20
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(..., description="Error type or code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        schema_extra = {
            "example": {
                "error": "BatchNotFoundError",
                "message": "Batch not found: 550e8400-e29b-41d4-a716-446655440000",
                "details": {"batch_id": "550e8400-e29b-41d4-a716-446655440000"}
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Framework version")
    database: str = Field(..., description="Database connection status")
    registered_batch_types: List[str] = Field(..., description="Available batch types")

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "database": "connected",
                "registered_batch_types": ["customer_data", "transaction_feed"]
            }
        }
