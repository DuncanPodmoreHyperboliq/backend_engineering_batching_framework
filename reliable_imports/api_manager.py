"""
REST API Manager for the Reliable Imports framework.

This module provides auto-generated REST APIs for batch operations,
with support for custom endpoint behavior overrides.
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse

from . import __version__
from .api_models import (
    CreateBatchRequest,
    CreateBatchResponse,
    ProcessBatchRequest,
    ProcessBatchResponse,
    ReprocessBatchRequest,
    ReprocessBatchResponse,
    BatchResponse,
    BatchSummaryResponse,
    BatchListResponse,
    ErrorResponse,
    HealthResponse,
    BatchItemResponse,
)
from .api_registry import EndpointRegistry, get_endpoint_registry
from .batch import BatchManager
from .endpoint import BaseEndpoint, EndpointContext
from .exceptions import (
    BatchNotFoundError,
    ProcessorNotFoundError,
    ValidationError as ImportValidationError,
)
from .models import BatchStatus, ItemStatus
from .registry import ProcessorRegistry


class APIManager:
    """
    Manages REST API endpoints for the Reliable Imports framework.

    The APIManager automatically generates CRUD endpoints for all registered
    batch types, while allowing custom behavior through endpoint overrides.

    Key features:
    - Auto-generated endpoints for create, process, reprocess, get, list
    - Custom endpoint hooks for validation, notifications, etc.
    - Comprehensive error handling
    - OpenAPI/Swagger documentation
    """

    def __init__(
        self,
        batch_manager: BatchManager,
        endpoint_registry: Optional[EndpointRegistry] = None,
        logger: Optional[logging.Logger] = None,
        title: str = "Reliable Imports API",
        description: str = "Auto-generated REST API for batch data imports",
        version: str = __version__,
    ):
        """
        Initialize the API manager.

        Args:
            batch_manager: BatchManager instance for processing operations
            endpoint_registry: Custom endpoint registry (uses global if not provided)
            logger: Logger instance
            title: API title for OpenAPI docs
            description: API description for OpenAPI docs
            version: API version
        """
        self.batch_manager = batch_manager
        self.endpoint_registry = endpoint_registry or get_endpoint_registry()
        self.logger = logger or logging.getLogger(__name__)

        # Create FastAPI app
        self.app = FastAPI(
            title=title,
            description=description,
            version=version,
            docs_url="/docs",
            redoc_url="/redoc",
        )

        # Register routes
        self._register_routes()
        self._register_error_handlers()

    def _get_custom_endpoint(self, batch_type: str) -> Optional[BaseEndpoint]:
        """Get custom endpoint instance for a batch type, if registered."""
        endpoint_class = self.endpoint_registry.get(batch_type)
        if endpoint_class:
            return endpoint_class()
        return None

    def _create_endpoint_context(self, request: Request) -> EndpointContext:
        """Create endpoint context from request."""
        # TODO: Extract user_id from auth headers/JWT if needed
        return EndpointContext(
            request=request,
            batch_manager=self.batch_manager,
            user_id=None,
        )

    def _register_routes(self):
        """Register all API routes."""

        @self.app.get("/", include_in_schema=False)
        async def root():
            """Root endpoint."""
            return {
                "name": "Reliable Imports API",
                "version": __version__,
                "docs": "/docs",
            }

        @self.app.get(
            "/health",
            response_model=HealthResponse,
            tags=["System"],
            summary="Health check",
        )
        async def health_check():
            """
            Check API and database health.

            Returns system status and available batch types.
            """
            try:
                # Test database connection
                self.batch_manager._get_connection().close()
                db_status = "connected"
            except Exception as e:
                db_status = f"error: {str(e)}"

            return HealthResponse(
                status="healthy" if db_status == "connected" else "unhealthy",
                version=__version__,
                database=db_status,
                registered_batch_types=self.batch_manager.registry.list_batch_types(),
            )

        @self.app.post(
            "/api/batches",
            response_model=CreateBatchResponse,
            tags=["Batches"],
            summary="Create a new batch",
            status_code=201,
        )
        async def create_batch(
            request_data: CreateBatchRequest,
            request: Request,
        ):
            """
            Create a new import batch.

            Optionally auto-process the batch by setting `auto_process: true`.
            """
            ctx = self._create_endpoint_context(request)
            custom_endpoint = self._get_custom_endpoint(request_data.batch_type)

            try:
                # Call before_create_batch hook if custom endpoint exists
                if custom_endpoint:
                    if not custom_endpoint.check_rate_limit(ctx):
                        raise HTTPException(
                            status_code=429,
                            detail="Rate limit exceeded"
                        )

                    max_size = custom_endpoint.get_max_batch_size(ctx)
                    if max_size and len(request_data.items) > max_size:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Batch size exceeds limit of {max_size}"
                        )

                    # Custom validation
                    errors = custom_endpoint.validate_create_batch_items(
                        request_data.items, ctx
                    )
                    if errors:
                        raise HTTPException(
                            status_code=400,
                            detail={"errors": errors}
                        )

                    request_data = custom_endpoint.before_create_batch(
                        request_data, ctx
                    )

                # Create the batch
                batch_id = self.batch_manager.create_batch(
                    batch_type=request_data.batch_type,
                    items=request_data.items,
                    source_info=request_data.source_info,
                    metadata=request_data.metadata,
                )

                # Call after_create_batch hook
                if custom_endpoint:
                    custom_endpoint.after_create_batch(batch_id, request_data, ctx)

                # Auto-process if requested
                status = BatchStatus.PENDING.value
                if request_data.auto_process:
                    self.batch_manager.process_batch(batch_id)
                    status = BatchStatus.PROCESSING.value

                return CreateBatchResponse(
                    batch_id=batch_id,
                    batch_type=request_data.batch_type,
                    total_items=len(request_data.items),
                    status=status,
                )

            except ProcessorNotFoundError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except ImportValidationError as e:
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get(
            "/api/batches/{batch_id}",
            response_model=BatchSummaryResponse,
            tags=["Batches"],
            summary="Get batch details",
        )
        async def get_batch(batch_id: UUID, request: Request):
            """
            Get detailed information about a batch.

            Returns batch metadata and processing statistics.
            """
            ctx = self._create_endpoint_context(request)

            try:
                summary = self.batch_manager.get_batch_summary(batch_id)

                # Check access permissions
                custom_endpoint = self._get_custom_endpoint(summary.batch_type)
                if custom_endpoint:
                    if not custom_endpoint.validate_batch_access(batch_id, ctx):
                        raise HTTPException(status_code=403, detail="Access denied")

                # Calculate derived fields
                success_rate = summary.success_rate
                items_per_second = summary.items_per_second

                return BatchSummaryResponse(
                    id=summary.id,
                    batch_type=summary.batch_type,
                    status=summary.status.value,
                    created_at=summary.created_at,
                    started_at=summary.started_at,
                    completed_at=summary.completed_at,
                    retry_count=summary.retry_count,
                    total_items=summary.total_items,
                    completed_items=summary.completed_items,
                    failed_items=summary.failed_items,
                    pending_items=summary.pending_items,
                    duration_seconds=summary.duration_seconds,
                    success_rate=success_rate,
                    items_per_second=items_per_second,
                )

            except BatchNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @self.app.post(
            "/api/batches/{batch_id}/process",
            response_model=ProcessBatchResponse,
            tags=["Batches"],
            summary="Process a batch",
        )
        async def process_batch(
            batch_id: UUID,
            request_data: ProcessBatchRequest,
            request: Request,
        ):
            """
            Process a pending batch.

            Processes all items in the batch and returns a summary.
            """
            ctx = self._create_endpoint_context(request)

            try:
                # Get batch info for custom endpoint lookup
                summary = self.batch_manager.get_batch_summary(batch_id)
                custom_endpoint = self._get_custom_endpoint(summary.batch_type)

                # Check access and call before hook
                if custom_endpoint:
                    if not custom_endpoint.validate_batch_access(batch_id, ctx):
                        raise HTTPException(status_code=403, detail="Access denied")

                    request_data = custom_endpoint.before_process_batch(
                        batch_id, request_data, ctx
                    )

                # Process the batch
                result_summary = self.batch_manager.process_batch(
                    batch_id,
                    continue_on_error=request_data.continue_on_error,
                )

                # Call after hook
                if custom_endpoint:
                    custom_endpoint.after_batch_complete(batch_id, result_summary, ctx)

                return ProcessBatchResponse(
                    batch_id=batch_id,
                    status=result_summary.status.value,
                    summary=BatchSummaryResponse(
                        id=result_summary.id,
                        batch_type=result_summary.batch_type,
                        status=result_summary.status.value,
                        created_at=result_summary.created_at,
                        started_at=result_summary.started_at,
                        completed_at=result_summary.completed_at,
                        retry_count=result_summary.retry_count,
                        total_items=result_summary.total_items,
                        completed_items=result_summary.completed_items,
                        failed_items=result_summary.failed_items,
                        pending_items=result_summary.pending_items,
                        duration_seconds=result_summary.duration_seconds,
                        success_rate=result_summary.success_rate,
                        items_per_second=result_summary.items_per_second,
                    ),
                )

            except BatchNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))
            except Exception as e:
                # Call error hook
                if custom_endpoint:
                    custom_endpoint.on_batch_error(batch_id, e, ctx)
                raise

        @self.app.post(
            "/api/batches/{batch_id}/reprocess",
            response_model=ReprocessBatchResponse,
            tags=["Batches"],
            summary="Reprocess a batch",
        )
        async def reprocess_batch(
            batch_id: UUID,
            request_data: ReprocessBatchRequest,
            request: Request,
        ):
            """
            Reprocess a failed batch.

            Creates a new batch with failed items and processes them.
            """
            ctx = self._create_endpoint_context(request)

            try:
                # Get batch info for custom endpoint lookup
                summary = self.batch_manager.get_batch_summary(batch_id)
                custom_endpoint = self._get_custom_endpoint(summary.batch_type)

                # Check access and call before hook
                if custom_endpoint:
                    if not custom_endpoint.validate_batch_access(batch_id, ctx):
                        raise HTTPException(status_code=403, detail="Access denied")

                    request_data = custom_endpoint.before_reprocess_batch(
                        batch_id, request_data, ctx
                    )

                # Reprocess the batch
                new_batch_id = self.batch_manager.reprocess_batch(
                    batch_id,
                    failed_items_only=request_data.failed_items_only,
                    continue_on_error=request_data.continue_on_error,
                )

                # Get new batch summary
                new_summary = self.batch_manager.get_batch_summary(new_batch_id)

                # Call after hook
                if custom_endpoint:
                    custom_endpoint.after_reprocess_complete(
                        batch_id, new_batch_id, new_summary, ctx
                    )

                items_count = (
                    summary.failed_items
                    if request_data.failed_items_only
                    else summary.total_items
                )

                return ReprocessBatchResponse(
                    original_batch_id=batch_id,
                    new_batch_id=new_batch_id,
                    items_to_reprocess=items_count,
                    status=new_summary.status.value,
                )

            except BatchNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

        @self.app.get(
            "/api/batches",
            response_model=BatchListResponse,
            tags=["Batches"],
            summary="List batches",
        )
        async def list_batches(
            request: Request,
            batch_type: Optional[str] = Query(None, description="Filter by batch type"),
            status: Optional[str] = Query(None, description="Filter by status"),
            offset: int = Query(0, ge=0, description="Pagination offset"),
            limit: int = Query(20, ge=1, le=100, description="Pagination limit"),
        ):
            """
            List batches with optional filters.

            Supports pagination and filtering by batch type and status.
            """
            ctx = self._create_endpoint_context(request)

            # Build query
            where_clauses = []
            params = []

            if batch_type:
                where_clauses.append("batch_type = %s")
                params.append(batch_type)

            if status:
                where_clauses.append("status = %s")
                params.append(status)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Execute query
            with self.batch_manager._get_connection() as conn:
                with conn.cursor() as cur:
                    # Get total count
                    cur.execute(
                        f"SELECT COUNT(*) FROM import_batches WHERE {where_sql}",
                        tuple(params),
                    )
                    total = cur.fetchone()[0]

                    # Get batches
                    cur.execute(
                        f"""
                        SELECT * FROM import_batch_summary
                        WHERE {where_sql}
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        tuple(params + [limit, offset]),
                    )

                    batches = []
                    for row in cur.fetchall():
                        batches.append(
                            BatchSummaryResponse(
                                id=UUID(row[0]),
                                batch_type=row[1],
                                status=row[2],
                                created_at=row[3],
                                started_at=row[4],
                                completed_at=row[5],
                                retry_count=row[6],
                                total_items=row[7],
                                completed_items=row[8],
                                failed_items=row[9],
                                pending_items=row[10],
                                duration_seconds=row[11],
                                success_rate=(row[8] / row[7] * 100) if row[7] > 0 else 0,
                                items_per_second=(row[7] / row[11]) if row[11] and row[11] > 0 else None,
                            )
                        )

            return BatchListResponse(
                batches=batches,
                total=total,
                offset=offset,
                limit=limit,
            )

    def _register_error_handlers(self):
        """Register global error handlers."""

        @self.app.exception_handler(BatchNotFoundError)
        async def batch_not_found_handler(request: Request, exc: BatchNotFoundError):
            return JSONResponse(
                status_code=404,
                content=ErrorResponse(
                    error="BatchNotFoundError",
                    message=str(exc),
                ).dict(),
            )

        @self.app.exception_handler(ProcessorNotFoundError)
        async def processor_not_found_handler(
            request: Request, exc: ProcessorNotFoundError
        ):
            return JSONResponse(
                status_code=400,
                content=ErrorResponse(
                    error="ProcessorNotFoundError",
                    message=str(exc),
                ).dict(),
            )

        @self.app.exception_handler(ImportValidationError)
        async def validation_error_handler(
            request: Request, exc: ImportValidationError
        ):
            return JSONResponse(
                status_code=400,
                content=ErrorResponse(
                    error="ValidationError",
                    message=str(exc),
                ).dict(),
            )

    def run(self, host: str = "0.0.0.0", port: int = 8000, **kwargs):
        """
        Run the API server using uvicorn.

        Args:
            host: Host to bind to
            port: Port to bind to
            **kwargs: Additional uvicorn options
        """
        import uvicorn

        uvicorn.run(self.app, host=host, port=port, **kwargs)
