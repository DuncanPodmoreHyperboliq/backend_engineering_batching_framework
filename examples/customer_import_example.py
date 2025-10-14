"""
Example: Customer Data Import

This example demonstrates how to use the Reliable Imports framework
to import customer data from a CSV file into a PostgreSQL database.

Key features demonstrated:
- Convention-based processor registration
- Batch creation and processing
- Error handling and validation
- Reprocessing failed imports
- Logging and monitoring

Time saved: Instead of writing hundreds of lines of boilerplate for
batch tracking, error handling, and reprocessing, this example shows
how the framework reduces it to ~50 lines of business logic.
"""

import csv
import sys
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, '..')

from reliable_imports import (
    BaseProcessor,
    BatchManager,
    ImportContext,
    ImportBatchItem,
    processor,
)


# Convention-based processor: CustomerDataProcessor handles 'customer_data' batch type
class CustomerDataProcessor(BaseProcessor):
    """
    Processor for customer data imports.

    The framework automatically registers this processor for batch_type='customer_data'
    based on the class name convention.
    """

    def validate_item(self, item: ImportBatchItem, ctx: ImportContext) -> bool:
        """Validate customer data before processing."""
        data = item.source_data

        # Required fields
        required = ['email', 'first_name', 'last_name']
        for field in required:
            if not data.get(field):
                ctx.warning(f"Missing required field: {field}")
                return False

        # Email validation
        if '@' not in data['email']:
            ctx.warning(f"Invalid email: {data['email']}")
            return False

        return True

    def process_item(self, item: ImportBatchItem, ctx: ImportContext) -> dict:
        """
        Process a single customer record.

        This is where your business logic lives. The framework handles:
        - Transaction management
        - Error handling and rollback
        - Status tracking
        - Logging
        """
        data = item.source_data

        ctx.info(f"Processing customer: {data['email']}")

        # Check if customer already exists
        existing = ctx.execute_one(
            "SELECT id FROM customers WHERE email = %s",
            (data['email'],)
        )

        if existing:
            # Update existing customer
            customer_id = existing['id']
            ctx.execute(
                """
                UPDATE customers
                SET first_name = %s,
                    last_name = %s,
                    phone = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    data['first_name'],
                    data['last_name'],
                    data.get('phone'),
                    customer_id,
                )
            )
            ctx.info(f"Updated existing customer: {customer_id}")
        else:
            # Create new customer
            customer_id = str(uuid4())
            ctx.execute(
                """
                INSERT INTO customers
                    (id, email, first_name, last_name, phone, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (
                    customer_id,
                    data['email'],
                    data['first_name'],
                    data['last_name'],
                    data.get('phone'),
                )
            )
            ctx.info(f"Created new customer: {customer_id}")

        # Return metadata about what was processed
        return {
            'target_table': 'customers',
            'target_id': customer_id,
            'processed_data': {
                'email': data['email'],
                'name': f"{data['first_name']} {data['last_name']}"
            }
        }

    def on_batch_start(self, ctx: ImportContext):
        """Hook called before batch processing starts."""
        ctx.info("Starting customer data import batch")

        # Example: Create customers table if it doesn't exist
        ctx.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id UUID PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                phone VARCHAR(20),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
        """)

    def on_batch_complete(self, ctx: ImportContext, success: bool):
        """Hook called after batch processing completes."""
        if success:
            ctx.info("Customer import batch completed successfully")
        else:
            ctx.error("Customer import batch completed with errors")


def load_customers_from_csv(file_path: str) -> list:
    """Load customer data from a CSV file."""
    customers = []

    with open(file_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            customers.append(row)

    return customers


def main():
    """
    Main example demonstrating the framework.

    This shows how simple it is to:
    1. Create a batch
    2. Process it
    3. Check results
    4. Reprocess failures
    """

    # Database connection
    conn_string = "postgresql://user:password@localhost:5432/mydb"

    # Initialize batch manager
    manager = BatchManager(conn_string)

    # Auto-discover processors (finds CustomerDataProcessor)
    manager.registry.discover('__main__')

    print("=== Reliable Imports Framework Demo ===\n")

    # Example 1: Create and process a batch
    print("1. Creating batch from sample data...")

    sample_data = [
        {
            'email': 'john@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'phone': '555-0100'
        },
        {
            'email': 'jane@example.com',
            'first_name': 'Jane',
            'last_name': 'Smith',
            'phone': '555-0101'
        },
        {
            'email': 'invalid-email',  # This will fail validation
            'first_name': 'Bad',
            'last_name': 'Data'
        },
        {
            'email': 'bob@example.com',
            'first_name': 'Bob',
            'last_name': 'Johnson',
            'phone': '555-0102'
        },
    ]

    batch_id = manager.create_batch(
        batch_type='customer_data',
        items=sample_data,
        source_info={'source': 'example', 'file': 'sample_data.csv'},
        metadata={'imported_by': 'demo_script'}
    )

    print(f"Created batch: {batch_id}\n")

    # Example 2: Process the batch
    print("2. Processing batch...")
    summary = manager.process_batch(batch_id)

    print(f"\nBatch Summary:")
    print(f"  Status: {summary.status}")
    print(f"  Total items: {summary.total_items}")
    print(f"  Completed: {summary.completed_items}")
    print(f"  Failed: {summary.failed_items}")
    print(f"  Success rate: {summary.success_rate:.1f}%")
    print(f"  Duration: {summary.duration_seconds:.2f}s")

    if summary.items_per_second:
        print(f"  Throughput: {summary.items_per_second:.1f} items/sec")

    # Example 3: Reprocess failed items
    if summary.failed_items > 0:
        print(f"\n3. Reprocessing {summary.failed_items} failed items...")

        # This creates a new batch with only the failed items
        # and automatically processes it
        new_batch_id = manager.reprocess_batch(
            batch_id,
            failed_items_only=True
        )

        print(f"Created reprocess batch: {new_batch_id}")

        new_summary = manager.get_batch_summary(new_batch_id)
        print(f"  Reprocess status: {new_summary.status}")
        print(f"  Completed: {new_summary.completed_items}/{new_summary.total_items}")

    print("\n=== Demo Complete ===")
    print("\nTime saved: Without this framework, you would need to write:")
    print("  - Batch tracking tables and queries")
    print("  - Transaction management code")
    print("  - Error handling and retry logic")
    print("  - Logging infrastructure")
    print("  - Reprocessing functionality")
    print("\nInstead, you wrote ~50 lines of business logic!")


if __name__ == '__main__':
    main()
