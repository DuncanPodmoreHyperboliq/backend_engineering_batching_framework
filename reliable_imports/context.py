"""
Import context provides the processing environment for batch operations.
"""

import logging
from typing import Any, Dict, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import ImportBatch, ImportBatchItem


class ImportContext:
    """
    Provides the execution context for processing batch items.

    The context encapsulates:
    - Database connection for transactional operations
    - Logging facility tied to the batch
    - Access to batch and item metadata
    - Helper methods for common operations

    This saves developer time by providing a consistent interface for all
    data operations within a batch.
    """

    def __init__(
        self,
        conn: psycopg2.extensions.connection,
        batch: ImportBatch,
        item: Optional[ImportBatchItem] = None,
        logger: Optional[logging.Logger] = None,
    ):
        self.conn = conn
        self.batch = batch
        self.item = item
        self.logger = logger or logging.getLogger(__name__)
        self._metadata: Dict[str, Any] = {}

    def log(self, level: str, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Log a message associated with the current batch/item.

        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            details: Optional structured details
        """
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO import_logs (batch_id, item_id, log_level, message, details)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    str(self.batch.id),
                    str(self.item.id) if self.item else None,
                    level,
                    message,
                    psycopg2.extras.Json(details) if details else None,
                ),
            )

        # Also log to Python logger
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{self.batch.batch_type}] {message}", extra=details or {})

    def info(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log an info message."""
        self.log("info", message, details)

    def warning(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log a warning message."""
        self.log("warning", message, details)

    def error(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log an error message."""
        self.log("error", message, details)

    def debug(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Log a debug message."""
        self.log("debug", message, details)

    def execute(self, query: str, params: Optional[tuple] = None) -> Any:
        """
        Execute a SQL query and return results.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            Query results
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return None

    def execute_one(self, query: str, params: Optional[tuple] = None) -> Optional[Dict]:
        """Execute a query and return the first result."""
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchone()
            return None

    def set_metadata(self, key: str, value: Any):
        """Set a metadata value for the current processing context."""
        self._metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get a metadata value from the current processing context."""
        return self._metadata.get(key, default)

    def get_all_metadata(self) -> Dict[str, Any]:
        """Get all metadata for the current processing context."""
        return self._metadata.copy()

    def is_reprocess(self) -> bool:
        """Check if this batch is a reprocessing operation."""
        return self.batch.parent_batch_id is not None

    def get_original_batch_id(self) -> UUID:
        """
        Get the original batch ID (useful for reprocessing scenarios).

        Returns the parent batch ID if this is a reprocess, otherwise the current batch ID.
        """
        return self.batch.parent_batch_id or self.batch.id
