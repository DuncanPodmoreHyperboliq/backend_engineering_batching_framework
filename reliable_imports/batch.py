"""
Batch manager for orchestrating import operations.

This is the main entry point for the framework, providing methods to:
- Create new batches
- Process batches
- Reprocess failed batches
- Query batch status
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import RealDictCursor

from .context import ImportContext
from .exceptions import BatchNotFoundError, ProcessorNotFoundError, ProcessingError
from .models import (
    BatchStatus,
    ImportBatch,
    ImportBatchItem,
    ItemStatus,
    BatchSummary,
)
from .processor import BaseProcessor
from .registry import ProcessorRegistry, get_registry


class BatchManager:
    """
    Manages the lifecycle of import batches.

    The BatchManager is designed to minimize developer time by:
    - Providing simple APIs for common operations
    - Handling transactions automatically
    - Managing error recovery and retries
    - Supporting easy reprocessing of failed imports
    """

    def __init__(
        self,
        connection_string: str,
        registry: Optional[ProcessorRegistry] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize the batch manager.

        Args:
            connection_string: PostgreSQL connection string
            registry: Processor registry (uses global if not provided)
            logger: Logger instance
        """
        self.connection_string = connection_string
        self.registry = registry or get_registry()
        self.logger = logger or logging.getLogger(__name__)

    def _get_connection(self):
        """Create a new database connection."""
        return psycopg2.connect(self.connection_string)

    def create_batch(
        self,
        batch_type: str,
        items: List[Dict[str, Any]],
        source_info: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> UUID:
        """
        Create a new import batch with items.

        Args:
            batch_type: Type of batch (must have a registered processor)
            items: List of source data items to process
            source_info: Metadata about the data source
            metadata: Additional batch metadata

        Returns:
            The batch ID (UUID)

        Raises:
            ProcessorNotFoundError: If no processor is registered for batch_type
        """
        # Verify processor exists
        if not self.registry.has(batch_type):
            raise ProcessorNotFoundError(
                f"No processor registered for batch type: {batch_type}"
            )

        batch_id = uuid4()

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Create batch
                cur.execute(
                    """
                    INSERT INTO import_batches
                        (id, batch_type, status, source_info, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        str(batch_id),
                        batch_type,
                        BatchStatus.PENDING.value,
                        psycopg2.extras.Json(source_info or {}),
                        psycopg2.extras.Json(metadata or {}),
                    ),
                )

                # Create batch items
                for idx, item_data in enumerate(items):
                    cur.execute(
                        """
                        INSERT INTO import_batch_items
                            (id, batch_id, item_index, status, source_data)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid4()),
                            str(batch_id),
                            idx,
                            ItemStatus.PENDING.value,
                            psycopg2.extras.Json(item_data),
                        ),
                    )

                conn.commit()

        self.logger.info(
            f"Created batch {batch_id} with {len(items)} items (type: {batch_type})"
        )

        return batch_id

    def process_batch(
        self, batch_id: UUID, continue_on_error: bool = True
    ) -> BatchSummary:
        """
        Process a batch.

        This method:
        1. Loads the batch and its items
        2. Instantiates the appropriate processor
        3. Processes each item in a transaction
        4. Updates batch status
        5. Returns a summary

        Args:
            batch_id: The batch to process
            continue_on_error: Whether to continue processing if an item fails

        Returns:
            Batch summary with statistics

        Raises:
            BatchNotFoundError: If the batch doesn't exist
            ProcessorNotFoundError: If no processor is registered
        """
        with self._get_connection() as conn:
            # Load batch
            batch = self._load_batch(conn, batch_id)
            if not batch:
                raise BatchNotFoundError(f"Batch not found: {batch_id}")

            # Get processor
            processor_class = self.registry.get(batch.batch_type)
            processor = processor_class()

            # Update batch status to processing
            self._update_batch_status(conn, batch_id, BatchStatus.PROCESSING)
            batch.status = BatchStatus.PROCESSING
            batch.started_at = datetime.utcnow()

            # Create context
            ctx = ImportContext(conn, batch, logger=self.logger)

            try:
                # Validate batch
                if not processor.validate_batch(ctx):
                    raise ProcessingError("Batch validation failed")

                # Call on_batch_start hook
                processor.on_batch_start(ctx)

                # Load and process items
                items = self._load_batch_items(conn, batch_id)
                success_count = 0
                failed_count = 0

                for item in items:
                    try:
                        # Update item context
                        ctx.item = item

                        # Skip if already processed
                        if item.is_complete():
                            continue

                        # Check if should skip
                        if processor.should_skip_item(item, ctx):
                            self._update_item_status(
                                conn, item.id, ItemStatus.SKIPPED
                            )
                            continue

                        # Validate item
                        if not processor.validate_item(item, ctx):
                            self._update_item_status(
                                conn, item.id, ItemStatus.SKIPPED
                            )
                            ctx.warning(f"Item {item.item_index} failed validation")
                            continue

                        # Process item
                        self._update_item_status(conn, item.id, ItemStatus.PROCESSING)

                        result = processor.process_item(item, ctx)

                        # Update item with results
                        self._complete_item(conn, item.id, result)
                        success_count += 1

                        conn.commit()

                    except Exception as e:
                        conn.rollback()
                        failed_count += 1

                        # Update item status
                        self._fail_item(conn, item.id, str(e))
                        conn.commit()

                        # Call error hook
                        should_continue = processor.on_item_error(item, e, ctx)

                        if not should_continue and not continue_on_error:
                            raise ProcessingError(
                                f"Batch processing aborted at item {item.item_index}: {e}"
                            )

                # Determine final batch status
                if failed_count == 0:
                    final_status = BatchStatus.COMPLETED
                elif success_count == 0:
                    final_status = BatchStatus.FAILED
                else:
                    # Partial success - mark as completed
                    final_status = BatchStatus.COMPLETED

                # Call completion hook
                processor.on_batch_complete(ctx, final_status == BatchStatus.COMPLETED)

                # Update batch status
                self._update_batch_status(
                    conn, batch_id, final_status, completed_at=datetime.utcnow()
                )

                conn.commit()

            except Exception as e:
                conn.rollback()
                self._update_batch_status(
                    conn, batch_id, BatchStatus.FAILED, error_message=str(e)
                )
                conn.commit()
                raise

            # Return summary
            return self.get_batch_summary(batch_id)

    def reprocess_batch(
        self,
        batch_id: UUID,
        failed_items_only: bool = True,
        continue_on_error: bool = True,
    ) -> UUID:
        """
        Reprocess a batch by creating a new batch with the same items.

        This is a key time-saving feature: instead of manually identifying and
        re-importing failed data, you can simply reprocess with one command.

        Args:
            batch_id: The original batch to reprocess
            failed_items_only: If True, only reprocess failed items
            continue_on_error: Whether to continue if an item fails

        Returns:
            The new batch ID

        Raises:
            BatchNotFoundError: If the original batch doesn't exist
        """
        with self._get_connection() as conn:
            # Load original batch
            original_batch = self._load_batch(conn, batch_id)
            if not original_batch:
                raise BatchNotFoundError(f"Batch not found: {batch_id}")

            # Load items to reprocess
            if failed_items_only:
                items = self._load_batch_items(
                    conn, batch_id, status_filter=ItemStatus.FAILED
                )
            else:
                items = self._load_batch_items(conn, batch_id)

            if not items:
                self.logger.info(f"No items to reprocess for batch {batch_id}")
                return batch_id

            # Create new batch with same source data
            new_batch_id = uuid4()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO import_batches
                        (id, batch_type, status, source_info, metadata, parent_batch_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(new_batch_id),
                        original_batch.batch_type,
                        BatchStatus.PENDING.value,
                        psycopg2.extras.Json(original_batch.source_info or {}),
                        psycopg2.extras.Json(original_batch.metadata or {}),
                        str(batch_id),
                    ),
                )

                # Copy items
                for idx, item in enumerate(items):
                    cur.execute(
                        """
                        INSERT INTO import_batch_items
                            (id, batch_id, item_index, status, source_data)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid4()),
                            str(new_batch_id),
                            idx,
                            ItemStatus.PENDING.value,
                            psycopg2.extras.Json(item.source_data),
                        ),
                    )

                conn.commit()

            self.logger.info(
                f"Created reprocess batch {new_batch_id} "
                f"from {batch_id} with {len(items)} items"
            )

        # Process the new batch
        self.process_batch(new_batch_id, continue_on_error=continue_on_error)

        return new_batch_id

    def get_batch_summary(self, batch_id: UUID) -> BatchSummary:
        """Get summary statistics for a batch."""
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM import_batch_summary WHERE id = %s",
                    (str(batch_id),),
                )
                row = cur.fetchone()

                if not row:
                    raise BatchNotFoundError(f"Batch not found: {batch_id}")

                return BatchSummary(
                    id=UUID(row["id"]),
                    batch_type=row["batch_type"],
                    status=BatchStatus(row["status"]),
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    retry_count=row["retry_count"],
                    total_items=row["total_items"],
                    completed_items=row["completed_items"],
                    failed_items=row["failed_items"],
                    pending_items=row["pending_items"],
                    duration_seconds=row["duration_seconds"],
                )

    def _load_batch(self, conn, batch_id: UUID) -> Optional[ImportBatch]:
        """Load a batch from the database."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM import_batches WHERE id = %s", (str(batch_id),)
            )
            row = cur.fetchone()

            if not row:
                return None

            return ImportBatch(
                id=UUID(row["id"]),
                batch_type=row["batch_type"],
                status=BatchStatus(row["status"]),
                source_info=row["source_info"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                error_message=row["error_message"],
                retry_count=row["retry_count"],
                parent_batch_id=UUID(row["parent_batch_id"])
                if row["parent_batch_id"]
                else None,
                metadata=row["metadata"] or {},
            )

    def _load_batch_items(
        self,
        conn,
        batch_id: UUID,
        status_filter: Optional[ItemStatus] = None,
    ) -> List[ImportBatchItem]:
        """Load batch items from the database."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status_filter:
                cur.execute(
                    """
                    SELECT * FROM import_batch_items
                    WHERE batch_id = %s AND status = %s
                    ORDER BY item_index
                    """,
                    (str(batch_id), status_filter.value),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM import_batch_items
                    WHERE batch_id = %s
                    ORDER BY item_index
                    """,
                    (str(batch_id),),
                )

            items = []
            for row in cur.fetchall():
                items.append(
                    ImportBatchItem(
                        id=UUID(row["id"]),
                        batch_id=UUID(row["batch_id"]),
                        item_index=row["item_index"],
                        status=ItemStatus(row["status"]),
                        source_data=row["source_data"],
                        processed_data=row["processed_data"],
                        target_table=row["target_table"],
                        target_id=UUID(row["target_id"]) if row["target_id"] else None,
                        error_message=row["error_message"],
                        processed_at=row["processed_at"],
                        created_at=row["created_at"],
                    )
                )

            return items

    def _update_batch_status(
        self,
        conn,
        batch_id: UUID,
        status: BatchStatus,
        error_message: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ):
        """Update batch status."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_batches
                SET status = %s,
                    error_message = %s,
                    completed_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (status.value, error_message, completed_at, str(batch_id)),
            )

    def _update_item_status(self, conn, item_id: UUID, status: ItemStatus):
        """Update item status."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_batch_items
                SET status = %s
                WHERE id = %s
                """,
                (status.value, str(item_id)),
            )

    def _complete_item(self, conn, item_id: UUID, result: Dict[str, Any]):
        """Mark item as completed with results."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_batch_items
                SET status = %s,
                    processed_data = %s,
                    target_table = %s,
                    target_id = %s,
                    processed_at = NOW()
                WHERE id = %s
                """,
                (
                    ItemStatus.COMPLETED.value,
                    psycopg2.extras.Json(result.get("processed_data")),
                    result.get("target_table"),
                    str(result["target_id"]) if result.get("target_id") else None,
                    str(item_id),
                ),
            )

    def _fail_item(self, conn, item_id: UUID, error_message: str):
        """Mark item as failed."""
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE import_batch_items
                SET status = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (ItemStatus.FAILED.value, error_message, str(item_id)),
            )
