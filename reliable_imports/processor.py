"""
Base processor class for implementing batch processing logic.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .context import ImportContext
from .models import ImportBatchItem


class BaseProcessor(ABC):
    """
    Abstract base class for batch processors.

    Convention: Processors should be named like `CustomerDataProcessor`
    for a batch_type of `customer_data`. The framework will automatically
    discover and register processors following this naming convention.

    This convention-based approach saves developer time by eliminating
    boilerplate registration code.
    """

    # Override in subclass to specify the batch type this processor handles
    batch_type: Optional[str] = None

    def __init__(self):
        """Initialize the processor."""
        if not self.batch_type:
            # Auto-derive batch_type from class name if not specified
            # E.g., CustomerDataProcessor -> customer_data
            class_name = self.__class__.__name__
            if class_name.endswith("Processor"):
                class_name = class_name[:-9]  # Remove "Processor"
            # Convert CamelCase to snake_case
            self.batch_type = self._camel_to_snake(class_name)

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert CamelCase to snake_case."""
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def validate_batch(self, ctx: ImportContext) -> bool:
        """
        Validate the entire batch before processing begins.

        Override this method to implement batch-level validation logic.
        Return False to abort the batch.

        Args:
            ctx: Import context

        Returns:
            True if batch is valid, False otherwise
        """
        return True

    @abstractmethod
    def validate_item(self, item: ImportBatchItem, ctx: ImportContext) -> bool:
        """
        Validate a single item before processing.

        Args:
            item: The batch item to validate
            ctx: Import context

        Returns:
            True if item is valid, False to skip the item
        """
        pass

    @abstractmethod
    def process_item(
        self, item: ImportBatchItem, ctx: ImportContext
    ) -> Dict[str, Any]:
        """
        Process a single batch item.

        This is where the main business logic lives. The method should:
        1. Transform the source_data
        2. Perform any necessary database operations
        3. Return processed data and metadata

        Args:
            item: The batch item to process
            ctx: Import context with database connection and logging

        Returns:
            Dict containing:
                - target_table: Name of the target table (optional)
                - target_id: ID of created/updated record (optional)
                - processed_data: Transformed data (optional)
                - Any other metadata you want to store
        """
        pass

    def on_batch_start(self, ctx: ImportContext):
        """
        Hook called when batch processing starts.

        Override this to perform setup operations like:
        - Creating temporary tables
        - Loading reference data
        - Initializing batch-level resources

        Args:
            ctx: Import context
        """
        pass

    def on_batch_complete(self, ctx: ImportContext, success: bool):
        """
        Hook called when batch processing completes.

        Override this to perform cleanup or finalization:
        - Updating aggregate tables
        - Sending notifications
        - Cleaning up temporary resources

        Args:
            ctx: Import context
            success: Whether the batch completed successfully
        """
        pass

    def on_item_error(
        self, item: ImportBatchItem, error: Exception, ctx: ImportContext
    ) -> bool:
        """
        Hook called when an item fails to process.

        Override this to implement custom error handling logic.

        Args:
            item: The failed batch item
            error: The exception that occurred
            ctx: Import context

        Returns:
            True to continue processing remaining items, False to abort the batch
        """
        ctx.error(f"Error processing item {item.item_index}: {str(error)}")
        return True  # Continue by default

    def get_batch_items(self, ctx: ImportContext) -> List[ImportBatchItem]:
        """
        Retrieve items for the current batch.

        Override this if you need custom logic for fetching batch items.
        By default, fetches all items from the database.

        Args:
            ctx: Import context

        Returns:
            List of batch items
        """
        # This will be implemented by the BatchManager
        # Subclasses can override for custom behavior
        pass

    def should_skip_item(self, item: ImportBatchItem, ctx: ImportContext) -> bool:
        """
        Determine if an item should be skipped.

        Override this to implement conditional processing logic.

        Args:
            item: The batch item
            ctx: Import context

        Returns:
            True to skip the item, False to process it
        """
        return False

    def transform_source_data(
        self, source_data: Dict[str, Any], ctx: ImportContext
    ) -> Dict[str, Any]:
        """
        Transform source data before processing.

        Override this for common transformations applied to all items.

        Args:
            source_data: Raw source data
            ctx: Import context

        Returns:
            Transformed data
        """
        return source_data

    def estimate_processing_time(self, item_count: int) -> float:
        """
        Estimate processing time in seconds for a given item count.

        Override this to provide better time estimates for monitoring.

        Args:
            item_count: Number of items to process

        Returns:
            Estimated time in seconds
        """
        # Default: assume 0.1 seconds per item
        return item_count * 0.1
