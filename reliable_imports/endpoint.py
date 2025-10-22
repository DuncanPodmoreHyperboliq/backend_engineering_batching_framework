"""
Base endpoint class for customizing REST API behavior per batch type.

This module provides the BaseEndpoint class that allows developers to
override default API behavior for specific batch types.
"""

from abc import ABC
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Request

from .api_models import CreateBatchRequest, ProcessBatchRequest, ReprocessBatchRequest
from .models import BatchSummary, ImportBatch


class EndpointContext:
    """
    Context object passed to endpoint hooks.

    Provides access to:
    - Request information
    - User/auth data (if available)
    - Batch manager instance
    """

    def __init__(
        self,
        request: Request,
        batch_manager: Any,  # BatchManager instance
        user_id: Optional[str] = None,
    ):
        self.request = request
        self.batch_manager = batch_manager
        self.user_id = user_id
        self._metadata: Dict[str, Any] = {}

    def set_metadata(self, key: str, value: Any):
        """Store custom metadata in the context."""
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Retrieve custom metadata from the context."""
        return self._metadata.get(key, default)

    @property
    def metadata(self) -> Dict[str, Any]:
        """Get all metadata."""
        return self._metadata.copy()


class BaseEndpoint(ABC):
    """
    Base class for custom endpoint behavior.

    Convention: Endpoints should be named like `CustomerDataEndpoint`
    to customize the API for the `customer_data` batch type.

    Example:
        >>> class CustomerDataEndpoint(BaseEndpoint):
        ...     batch_type = 'customer_data'
        ...
        ...     def before_create_batch(self, request_data, ctx):
        ...         # Add custom validation
        ...         if not self._check_quota(ctx.user_id):
        ...             raise ValueError("Quota exceeded")
        ...         return request_data
        ...
        ...     def after_batch_complete(self, batch_id, summary, ctx):
        ...         # Send notification
        ...         self._send_notification(summary)
    """

    # Override in subclass to specify the batch type this endpoint handles
    batch_type: Optional[str] = None

    def __init__(self):
        """Initialize the endpoint."""
        if not self.batch_type:
            # Auto-derive batch_type from class name if not specified
            # E.g., CustomerDataEndpoint -> customer_data
            class_name = self.__class__.__name__
            if class_name.endswith("Endpoint"):
                class_name = class_name[:-8]  # Remove "Endpoint"
            # Convert CamelCase to snake_case
            self.batch_type = self._camel_to_snake(class_name)

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    # ===== Lifecycle Hooks =====

    def before_create_batch(
        self, request_data: CreateBatchRequest, ctx: EndpointContext
    ) -> CreateBatchRequest:
        """
        Hook called before creating a batch.

        Override this to:
        - Validate request data
        - Enrich items with additional data
        - Check quotas or rate limits
        - Modify metadata

        Args:
            request_data: The incoming create batch request
            ctx: Endpoint context with request info

        Returns:
            Modified request data (or same object if no changes)

        Raises:
            ValueError, HTTPException: To reject the request
        """
        return request_data

    def after_create_batch(
        self, batch_id: UUID, request_data: CreateBatchRequest, ctx: EndpointContext
    ) -> Dict[str, Any]:
        """
        Hook called after a batch is created.

        Override this to:
        - Send notifications
        - Update external systems
        - Add custom response data

        Args:
            batch_id: ID of the created batch
            request_data: The original request
            ctx: Endpoint context

        Returns:
            Dict of additional data to include in response (optional)
        """
        return {}

    def before_process_batch(
        self, batch_id: UUID, request_data: ProcessBatchRequest, ctx: EndpointContext
    ) -> ProcessBatchRequest:
        """
        Hook called before processing a batch.

        Override this to:
        - Validate batch can be processed
        - Check permissions
        - Modify processing options

        Args:
            batch_id: ID of the batch to process
            request_data: Processing options
            ctx: Endpoint context

        Returns:
            Modified request data (or same object if no changes)

        Raises:
            ValueError, HTTPException: To reject the request
        """
        return request_data

    def after_batch_complete(
        self, batch_id: UUID, summary: BatchSummary, ctx: EndpointContext
    ) -> Dict[str, Any]:
        """
        Hook called after batch processing completes.

        Override this to:
        - Send completion notifications
        - Update dashboards
        - Trigger downstream processes
        - Add custom response data

        Args:
            batch_id: ID of the processed batch
            summary: Batch processing summary
            ctx: Endpoint context

        Returns:
            Dict of additional data to include in response (optional)
        """
        return {}

    def before_reprocess_batch(
        self, batch_id: UUID, request_data: ReprocessBatchRequest, ctx: EndpointContext
    ) -> ReprocessBatchRequest:
        """
        Hook called before reprocessing a batch.

        Override this to:
        - Validate reprocessing is allowed
        - Check permissions
        - Modify reprocessing options

        Args:
            batch_id: ID of the batch to reprocess
            request_data: Reprocessing options
            ctx: Endpoint context

        Returns:
            Modified request data (or same object if no changes)

        Raises:
            ValueError, HTTPException: To reject the request
        """
        return request_data

    def after_reprocess_complete(
        self,
        original_batch_id: UUID,
        new_batch_id: UUID,
        summary: BatchSummary,
        ctx: EndpointContext,
    ) -> Dict[str, Any]:
        """
        Hook called after batch reprocessing completes.

        Args:
            original_batch_id: ID of the original batch
            new_batch_id: ID of the new reprocessing batch
            summary: Processing summary
            ctx: Endpoint context

        Returns:
            Dict of additional data to include in response (optional)
        """
        return {}

    def on_batch_error(
        self, batch_id: UUID, error: Exception, ctx: EndpointContext
    ) -> Optional[Dict[str, Any]]:
        """
        Hook called when batch processing fails.

        Override this to:
        - Send error notifications
        - Log to external systems
        - Implement custom error handling

        Args:
            batch_id: ID of the failed batch
            error: The exception that occurred
            ctx: Endpoint context

        Returns:
            Optional dict with custom error details
        """
        return None

    # ===== Query Customization =====

    def get_list_filters(self, ctx: EndpointContext) -> Dict[str, Any]:
        """
        Provide additional filters for listing batches.

        Override this to:
        - Filter by user/tenant
        - Add business-specific filters

        Args:
            ctx: Endpoint context

        Returns:
            Dict of additional filter criteria
        """
        return {}

    def transform_batch_response(
        self, batch: ImportBatch, ctx: EndpointContext
    ) -> Dict[str, Any]:
        """
        Transform batch data before returning in API response.

        Override this to:
        - Add computed fields
        - Enrich with related data
        - Filter sensitive information

        Args:
            batch: The batch object
            ctx: Endpoint context

        Returns:
            Dict of additional fields to include in response
        """
        return {}

    # ===== Validation Helpers =====

    def validate_batch_access(
        self, batch_id: UUID, ctx: EndpointContext
    ) -> bool:
        """
        Check if the current user can access a batch.

        Override this to implement:
        - Multi-tenancy
        - Role-based access control
        - Custom permissions

        Args:
            batch_id: ID of the batch
            ctx: Endpoint context

        Returns:
            True if access is allowed, False otherwise

        Raises:
            HTTPException: To return custom error response
        """
        return True

    def validate_create_batch_items(
        self, items: List[Dict[str, Any]], ctx: EndpointContext
    ) -> List[str]:
        """
        Validate batch items before creation.

        Override this to implement custom validation logic.

        Args:
            items: List of items to validate
            ctx: Endpoint context

        Returns:
            List of validation error messages (empty if valid)
        """
        return []

    # ===== Rate Limiting & Quotas =====

    def check_rate_limit(self, ctx: EndpointContext) -> bool:
        """
        Check if the request should be rate limited.

        Override this to implement:
        - Per-user rate limiting
        - Quota enforcement
        - Throttling logic

        Args:
            ctx: Endpoint context

        Returns:
            True if request is allowed, False if rate limited

        Raises:
            HTTPException: To return custom rate limit response
        """
        return True

    def get_max_batch_size(self, ctx: EndpointContext) -> Optional[int]:
        """
        Get the maximum allowed batch size for this user/context.

        Override this to implement:
        - User-specific limits
        - Tier-based quotas

        Args:
            ctx: Endpoint context

        Returns:
            Maximum batch size, or None for no limit
        """
        return None
