"""
Example: Complete REST API setup with custom endpoint.

This example demonstrates:
1. Setting up a processor
2. Creating a custom endpoint with validation and hooks
3. Running the REST API server
4. Making API calls
"""

import logging
from uuid import uuid4

from reliable_imports import (
    BaseProcessor,
    BaseEndpoint,
    BatchManager,
    APIManager,
    ImportContext,
    ImportBatchItem,
    EndpointContext,
)
from reliable_imports.api_models import CreateBatchRequest


# ===== 1. Define the Processor =====

class CustomerDataProcessor(BaseProcessor):
    """
    Processor for customer data imports.

    Convention: Class name determines batch type.
    CustomerDataProcessor -> 'customer_data'
    """

    def validate_item(self, item: ImportBatchItem, ctx: ImportContext) -> bool:
        """Validate that customer has required fields."""
        data = item.source_data

        # Check required fields
        if not data.get('email') or '@' not in data['email']:
            ctx.warning(f"Item {item.item_index}: Invalid email")
            return False

        if not data.get('name'):
            ctx.warning(f"Item {item.item_index}: Missing name")
            return False

        return True

    def process_item(self, item: ImportBatchItem, ctx: ImportContext) -> dict:
        """Process a customer record."""
        data = item.source_data

        # Check if customer exists
        existing = ctx.execute_one(
            "SELECT id FROM customers WHERE email = %s",
            (data['email'],)
        )

        if existing:
            # Update existing customer
            ctx.execute(
                """
                UPDATE customers
                SET name = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (data['name'], existing['id'])
            )
            ctx.info(f"Updated customer: {data['email']}")
            customer_id = existing['id']
        else:
            # Create new customer
            customer_id = uuid4()
            ctx.execute(
                """
                INSERT INTO customers (id, email, name, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                """,
                (str(customer_id), data['email'], data['name'])
            )
            ctx.info(f"Created customer: {data['email']}")

        return {
            'target_table': 'customers',
            'target_id': customer_id,
            'processed_data': {
                'email': data['email'],
                'name': data['name'],
            }
        }

    def on_batch_complete(self, ctx: ImportContext, success: bool):
        """Called when batch processing completes."""
        if success:
            ctx.info("Customer batch processing completed successfully")
        else:
            ctx.error("Customer batch processing failed")


# ===== 2. Define Custom Endpoint =====

class CustomerDataEndpoint(BaseEndpoint):
    """
    Custom endpoint for customer_data batch type.

    Adds:
    - Email domain validation
    - Rate limiting
    - Slack notifications
    - Custom response enrichment
    """

    # Optional: explicitly set batch_type
    # batch_type = 'customer_data'
    # (It's auto-derived from class name if not set)

    def __init__(self):
        super().__init__()
        # Track rate limits per user (simplified example)
        self._rate_limits = {}

    def validate_create_batch_items(self, items, ctx: EndpointContext):
        """Custom validation before batch creation."""
        errors = []

        # Check for duplicate emails within the batch
        emails = [item.get('email') for item in items]
        if len(emails) != len(set(emails)):
            errors.append("Batch contains duplicate email addresses")

        # Validate email domains (example: only allow certain domains)
        allowed_domains = ['example.com', 'test.com', 'mycompany.com']
        for idx, item in enumerate(items):
            email = item.get('email', '')
            if '@' in email:
                domain = email.split('@')[1]
                if domain not in allowed_domains:
                    errors.append(
                        f"Item {idx}: Email domain '{domain}' not allowed. "
                        f"Allowed domains: {', '.join(allowed_domains)}"
                    )

        return errors

    def check_rate_limit(self, ctx: EndpointContext) -> bool:
        """
        Check rate limits.

        In production, this would check Redis or similar.
        """
        user_id = ctx.user_id or 'anonymous'

        # Simple rate limit: max 10 batches per user
        # (In production, this would be time-based)
        count = self._rate_limits.get(user_id, 0)
        if count >= 10:
            return False

        self._rate_limits[user_id] = count + 1
        return True

    def get_max_batch_size(self, ctx: EndpointContext) -> int:
        """Limit batch size to prevent resource exhaustion."""
        # Could vary by user tier
        return 1000

    def before_create_batch(
        self, request_data: CreateBatchRequest, ctx: EndpointContext
    ) -> CreateBatchRequest:
        """Hook called before creating a batch."""
        # Enrich metadata
        if not request_data.metadata:
            request_data.metadata = {}

        request_data.metadata['api_version'] = 'v1'
        request_data.metadata['user_id'] = ctx.user_id or 'anonymous'

        # Could add more enrichment here
        # - Geocode addresses
        # - Validate against external APIs
        # - Normalize data

        return request_data

    def after_create_batch(self, batch_id, request_data, ctx: EndpointContext):
        """Hook called after batch is created."""
        # Send notification
        self._send_notification(
            f"New customer batch created: {batch_id} "
            f"({len(request_data.items)} items)"
        )

        return {
            'notification_sent': True
        }

    def after_batch_complete(self, batch_id, summary, ctx: EndpointContext):
        """Hook called after batch processing completes."""
        # Send completion notification with stats
        self._send_notification(
            f"Customer batch {batch_id} completed!\n"
            f"Success rate: {summary.success_rate:.1f}%\n"
            f"Completed: {summary.completed_items}/{summary.total_items}"
        )

        # Could trigger downstream processes
        # - Update analytics dashboard
        # - Trigger email campaigns
        # - Sync to CRM

        return {
            'notification_sent': True,
            'dashboard_updated': True
        }

    def on_batch_error(self, batch_id, error, ctx: EndpointContext):
        """Hook called when batch processing fails."""
        self._send_notification(
            f"⚠️ Customer batch {batch_id} failed: {str(error)}"
        )

        return {
            'error_notification_sent': True
        }

    def _send_notification(self, message: str):
        """
        Send notification to Slack/Teams/etc.

        In production, this would use actual webhook.
        """
        print(f"[NOTIFICATION] {message}")


# ===== 3. Setup and Run =====

def setup_api():
    """
    Setup the complete API with processors and custom endpoints.
    """
    # Database connection
    conn_string = "postgresql://user:password@localhost:5432/mydb"

    # Create batch manager
    batch_manager = BatchManager(conn_string)

    # Auto-discover processors
    # In this example, we'll register manually
    batch_manager.registry.register('customer_data', CustomerDataProcessor)

    # Create API manager
    api_manager = APIManager(
        batch_manager=batch_manager,
        title="Customer Import API",
        description="Auto-generated REST API for customer data imports",
    )

    # Auto-discover custom endpoints
    # Since we're in the same file, register manually
    api_manager.endpoint_registry.register('customer_data', CustomerDataEndpoint)

    return api_manager


# ===== 4. Example Usage =====

def run_server():
    """Run the API server."""
    api_manager = setup_api()

    print("=" * 60)
    print("🚀 Starting Reliable Imports API Server")
    print("=" * 60)
    print("\nAPI Documentation available at:")
    print("  • Swagger UI: http://localhost:8000/docs")
    print("  • ReDoc:      http://localhost:8000/redoc")
    print("\nEndpoints:")
    print("  POST   /api/batches              - Create batch")
    print("  GET    /api/batches              - List batches")
    print("  GET    /api/batches/{id}         - Get batch details")
    print("  POST   /api/batches/{id}/process - Process batch")
    print("  POST   /api/batches/{id}/reprocess - Reprocess batch")
    print("  GET    /health                   - Health check")
    print("\n" + "=" * 60)

    # Run server
    api_manager.run(host="0.0.0.0", port=8000)


def example_api_calls():
    """
    Example API calls using requests library.

    Run this after the server is running to test the API.
    """
    import requests

    base_url = "http://localhost:8000"

    # 1. Health check
    print("\n1. Health Check")
    print("-" * 40)
    response = requests.get(f"{base_url}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

    # 2. Create a batch
    print("2. Create Batch")
    print("-" * 40)
    response = requests.post(
        f"{base_url}/api/batches",
        json={
            "batch_type": "customer_data",
            "items": [
                {"email": "john@example.com", "name": "John Doe"},
                {"email": "jane@example.com", "name": "Jane Smith"},
                {"email": "bob@test.com", "name": "Bob Johnson"},
            ],
            "source_info": {"file": "customers_2024.csv"},
            "auto_process": False,  # Don't auto-process
        }
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

    batch_id = response.json()['batch_id']

    # 3. Get batch details
    print("3. Get Batch Details")
    print("-" * 40)
    response = requests.get(f"{base_url}/api/batches/{batch_id}")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

    # 4. Process the batch
    print("4. Process Batch")
    print("-" * 40)
    response = requests.post(
        f"{base_url}/api/batches/{batch_id}/process",
        json={"continue_on_error": True}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

    # 5. List all batches
    print("5. List Batches")
    print("-" * 40)
    response = requests.get(
        f"{base_url}/api/batches",
        params={"batch_type": "customer_data", "limit": 10}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")

    # 6. Reprocess failed items (if any)
    print("6. Reprocess Batch (failed items only)")
    print("-" * 40)
    response = requests.post(
        f"{base_url}/api/batches/{batch_id}/reprocess",
        json={"failed_items_only": True, "continue_on_error": True}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Run API call examples
        print("\n" + "=" * 60)
        print("Running API Test Examples")
        print("=" * 60)
        example_api_calls()
    else:
        # Run server
        run_server()
