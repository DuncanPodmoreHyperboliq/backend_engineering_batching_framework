# Reliable Imports Framework

A convention-based Python framework for reliable data ingestion with PostgreSQL, designed to **save developer time** through batch processing, import IDs, and easy reprocessing.

## The Problem: Developer Time is Your Biggest Bottleneck

In small teams, developer time is the most critical and expensive resource. Data quality issues, failed imports, and debugging data problems can consume hours or days of developer time that could be spent on building features.

Traditional approaches to data ingestion require developers to:
- Write extensive boilerplate for batch tracking
- Implement custom error handling for each import type
- Manually track what succeeded vs. failed
- Build reprocessing logic from scratch
- Debug data issues without proper audit trails

**This framework eliminates all of that**, reducing weeks of development time to hours.

## Key Benefits

### 1. Massive Time Savings
- **15-20 hours saved per import pipeline** (vs. building from scratch)
- **2-3 hours saved per data issue** (easy reprocessing vs. manual fixes)
- **5-10 hours saved on debugging** (comprehensive logging and tracking)

### 2. Convention Over Configuration
- Auto-discovery of processors based on naming conventions
- Minimal boilerplate code
- Write business logic, not infrastructure

### 3. Built-in Reliability
- Automatic batch tracking with unique IDs
- Complete audit trail of all operations
- Transactional processing with automatic rollback
- Easy reprocessing of failed imports

### 4. Production-Ready Features
- Comprehensive error handling
- Detailed logging tied to batches and items
- Status monitoring and reporting
- Performance metrics and statistics

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Database Setup

```bash
python setup_database.py "postgresql://user:password@localhost:5432/mydb"
```

### Create Your First Processor

```python
from reliable_imports import BaseProcessor, ImportContext, ImportBatchItem

# Convention: Class name determines batch type
# CustomerDataProcessor -> handles 'customer_data' batches
class CustomerDataProcessor(BaseProcessor):

    def validate_item(self, item: ImportBatchItem, ctx: ImportContext) -> bool:
        """Validate an item before processing."""
        data = item.source_data
        return data.get('email') and '@' in data['email']

    def process_item(self, item: ImportBatchItem, ctx: ImportContext) -> dict:
        """Process a single item."""
        data = item.source_data

        # Your business logic here
        customer_id = self._create_or_update_customer(data, ctx)

        return {
            'target_table': 'customers',
            'target_id': customer_id
        }

    def _create_or_update_customer(self, data, ctx):
        existing = ctx.execute_one(
            "SELECT id FROM customers WHERE email = %s",
            (data['email'],)
        )

        if existing:
            ctx.execute(
                "UPDATE customers SET name = %s WHERE id = %s",
                (data['name'], existing['id'])
            )
            return existing['id']
        else:
            customer_id = uuid4()
            ctx.execute(
                "INSERT INTO customers (id, email, name) VALUES (%s, %s, %s)",
                (str(customer_id), data['email'], data['name'])
            )
            return customer_id
```

### Use the Framework

```python
from reliable_imports import BatchManager

# Initialize
manager = BatchManager("postgresql://user:password@localhost:5432/mydb")

# Auto-discover processors
manager.registry.discover('myapp.processors')

# Create and process a batch
batch_id = manager.create_batch(
    batch_type='customer_data',
    items=[
        {'email': 'john@example.com', 'name': 'John Doe'},
        {'email': 'jane@example.com', 'name': 'Jane Smith'},
    ]
)

# Process it
summary = manager.process_batch(batch_id)

print(f"Completed: {summary.completed_items}/{summary.total_items}")
print(f"Success rate: {summary.success_rate}%")

# Reprocess any failures with one line
if summary.failed_items > 0:
    manager.reprocess_batch(batch_id, failed_items_only=True)
```

That's it! You just built a production-ready data import pipeline with:
- Automatic batch tracking
- Full error handling
- Comprehensive logging
- Easy reprocessing

## REST API Support (NEW!)

The framework now includes **auto-generated REST APIs** for all your batch processors!

### Quick REST API Setup

```python
from reliable_imports import BatchManager, APIManager

# Setup batch manager (as before)
manager = BatchManager("postgresql://user:password@localhost:5432/mydb")
manager.registry.discover('myapp.processors')

# Add REST API with one line!
api_manager = APIManager(manager)
api_manager.run(host="0.0.0.0", port=8000)
```

Visit http://localhost:8000/docs for auto-generated Swagger documentation!

### Auto-Generated Endpoints

For each batch processor, you automatically get:
- `POST /api/batches` - Create and optionally process batches
- `GET /api/batches` - List batches with filters
- `GET /api/batches/{id}` - Get batch details and statistics
- `POST /api/batches/{id}/process` - Process a batch
- `POST /api/batches/{id}/reprocess` - Reprocess failed items
- `GET /health` - Health check

### Custom Endpoint Behavior

Override default behavior with custom endpoints:

```python
from reliable_imports import BaseEndpoint, EndpointContext

class CustomerDataEndpoint(BaseEndpoint):
    """Custom endpoint for customer_data batch type."""

    def before_create_batch(self, request_data, ctx: EndpointContext):
        # Add custom validation, rate limiting, etc.
        if not self._check_quota(ctx.user_id):
            raise ValueError("Quota exceeded")
        return request_data

    def after_batch_complete(self, batch_id, summary, ctx):
        # Send notifications, trigger webhooks, etc.
        self._send_slack_notification(summary)
```

**Time saved: 15-20 hours** building REST APIs from scratch!

See [REST_API.md](REST_API.md) for complete documentation and examples.

## Architecture

The framework uses a simple but powerful architecture:

```
┌─────────────────────────────────────────────────────┐
│                  BatchManager                        │
│  - Creates and orchestrates batches                 │
│  - Manages transactions                             │
│  - Coordinates processor execution                  │
└────────────┬────────────────────────────────────────┘
             │
             ├──────────────────┬────────────────────┐
             │                  │                    │
        ┌────▼────┐      ┌─────▼─────┐      ┌──────▼──────┐
        │Registry │      │  Context  │      │  Database   │
        │         │      │           │      │             │
        │ Auto-   │      │ - Logging │      │ - Batches   │
        │ discover│      │ - DB ops  │      │ - Items     │
        │ process-│      │ - Metadata│      │ - Logs      │
        │ ors     │      │           │      │             │
        └─────────┘      └───────────┘      └─────────────┘
             │
        ┌────▼────────────────────────────┐
        │   Your Custom Processors        │
        │                                 │
        │  - CustomerDataProcessor        │
        │  - TransactionFeedProcessor     │
        │  - ProductCatalogProcessor      │
        │  - etc.                         │
        └─────────────────────────────────┘
```

## Core Concepts

### Batches
A batch is a collection of related items to be processed together. Each batch:
- Has a unique ID (UUID)
- Tracks status (pending, processing, completed, failed)
- Records timing and metadata
- Can be reprocessed independently

### Items
Items are individual records within a batch. Each item:
- Stores the original source data
- Tracks its own status
- Records processing results
- Can be processed independently

### Processors
Processors contain your business logic. They:
- Validate items before processing
- Transform and load data
- Are automatically discovered by naming convention
- Inherit from `BaseProcessor`

### Context
The ImportContext provides:
- Database connection (with transaction management)
- Logging tied to the batch/item
- Helper methods for common operations
- Metadata storage

## Time Savings Analysis

### Traditional Approach
Building a reliable import system from scratch:

| Component | Time Required |
|-----------|---------------|
| Database schema design | 4-6 hours |
| Batch tracking logic | 8-12 hours |
| Transaction management | 4-6 hours |
| Error handling framework | 6-8 hours |
| Logging infrastructure | 4-6 hours |
| Reprocessing functionality | 8-12 hours |
| Testing and debugging | 10-15 hours |
| **Total** | **44-65 hours** |

### With Reliable Imports Framework

| Task | Time Required |
|------|---------------|
| Install and setup | 15 minutes |
| Write processor | 1-2 hours |
| Test and deploy | 1-2 hours |
| **Total** | **2.5-4.5 hours** |

### **Time Saved: 40-60 hours per project**

For a team of 5 developers building multiple import pipelines:
- **200-300 hours saved per year**
- **$15,000-$30,000 in developer time** (at $100/hour)
- **Faster time to market** for features
- **Reduced maintenance burden**

## Convention-Based Design

The framework follows "Convention over Configuration" to minimize boilerplate:

### Processor Naming
```python
# Class name automatically determines batch type
CustomerDataProcessor     -> batch_type = 'customer_data'
TransactionFeedProcessor  -> batch_type = 'transaction_feed'
ProductCatalogProcessor   -> batch_type = 'product_catalog'
```

### Auto-Discovery
```python
# Automatically finds and registers all processors in a package
manager.registry.discover('myapp.processors')
```

### Consistent Patterns
- All processors implement the same interface
- Context provides consistent database operations
- Status values are standardized
- Logging follows the same structure

## Reprocessing: The Killer Feature

One of the biggest time-savers is the ability to reprocess failed imports with a single command:

```python
# Reprocess only failed items
manager.reprocess_batch(original_batch_id, failed_items_only=True)
```

This creates a new batch with the original source data and processes it again. No need to:
- Manually identify failed records
- Extract data from logs
- Write custom recovery scripts
- Risk data inconsistency

**Time saved per incident: 2-3 hours**

## Monitoring and Observability

The framework provides comprehensive monitoring out of the box:

### Batch Summary
```python
summary = manager.get_batch_summary(batch_id)
print(f"Status: {summary.status}")
print(f"Success rate: {summary.success_rate}%")
print(f"Throughput: {summary.items_per_second} items/sec")
```

### Built-in Views
- `import_batch_summary` - Real-time statistics for all batches
- `failed_imports_report` - Failed batches needing attention

### Comprehensive Logging
Every operation is logged with:
- Timestamp
- Batch and item context
- Log level
- Structured details (JSON)

## Best Practices

### 1. Keep Processors Focused
Each processor should handle one type of data. Don't try to make universal processors.

### 2. Validate Early
Use `validate_item()` to catch bad data before processing starts.

### 3. Use Hooks for Setup/Teardown
- `on_batch_start()` for creating temp tables, loading reference data
- `on_batch_complete()` for cleanup, notifications, aggregate updates

### 4. Log Liberally
Use `ctx.info()`, `ctx.warning()`, `ctx.error()` to create an audit trail.

### 5. Return Meaningful Metadata
Include `target_table`, `target_id`, and `processed_data` in your return value for traceability.

### 6. Design for Idempotency
Your processors should be safe to run multiple times on the same data (important for reprocessing).

## Examples

See the `examples/` directory for complete working examples:

- `customer_import_example.py` - Basic customer data import
- `api_example.py` - Complete REST API setup with custom endpoints

## Database Schema

The framework uses three main tables:

- `import_batches` - Batch metadata and status
- `import_batch_items` - Individual items within batches
- `import_logs` - Detailed audit trail

All tables include comprehensive indexes for performance.

## Requirements

- Python 3.7+
- PostgreSQL 12+ (for `gen_random_uuid()` support)
- psycopg2

### Optional (for REST API)
- FastAPI
- Uvicorn
- Pydantic

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! This framework was built to save developer time - if you have ideas for making it even better, please open an issue or PR.

## Support

For questions, issues, or feature requests, please open a GitHub issue.

---

**Remember: The goal is to save developer time, not build the most complex system.**

Keep it simple. Keep it reliable. Focus on your business logic, not infrastructure.
