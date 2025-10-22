# REST API Documentation

The Reliable Imports Framework now includes **auto-generated REST APIs** for all your batch processors, saving even more developer time!

## Why REST APIs?

REST APIs are almost always needed alongside database import systems. Instead of building them from scratch each time, the framework now auto-generates production-ready APIs with:

- **Auto-generated CRUD endpoints** for all batch types
- **OpenAPI/Swagger documentation** out of the box
- **Custom endpoint overrides** for validation, notifications, and business logic
- **Comprehensive error handling**
- **Request/response validation** with Pydantic

**Time saved: 15-20 hours per project** compared to building REST APIs manually.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The REST API requires:
- `fastapi` - Modern web framework
- `uvicorn` - ASGI server
- `pydantic` - Data validation

### 2. Create Your API

```python
from reliable_imports import BatchManager, APIManager

# Setup batch manager (as before)
batch_manager = BatchManager("postgresql://user:password@localhost:5432/mydb")
batch_manager.registry.discover('myapp.processors')

# Create API manager - that's it!
api_manager = APIManager(batch_manager)

# Run the server
api_manager.run(host="0.0.0.0", port=8000)
```

### 3. Access Your API

Open your browser to:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You now have a fully functional REST API with auto-generated documentation!

## Auto-Generated Endpoints

For each registered batch processor, you automatically get these endpoints:

### Create Batch
```http
POST /api/batches
Content-Type: application/json

{
  "batch_type": "customer_data",
  "items": [
    {"email": "john@example.com", "name": "John Doe"},
    {"email": "jane@example.com", "name": "Jane Smith"}
  ],
  "source_info": {"file": "customers.csv"},
  "auto_process": true
}
```

**Response:**
```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "batch_type": "customer_data",
  "total_items": 2,
  "status": "processing",
  "message": "Batch created successfully"
}
```

### Get Batch Details
```http
GET /api/batches/{batch_id}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "batch_type": "customer_data",
  "status": "completed",
  "total_items": 2,
  "completed_items": 2,
  "failed_items": 0,
  "pending_items": 0,
  "success_rate": 100.0,
  "items_per_second": 10.5,
  "created_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:00:15Z"
}
```

### List Batches
```http
GET /api/batches?batch_type=customer_data&status=completed&limit=20&offset=0
```

**Response:**
```json
{
  "batches": [...],
  "total": 50,
  "offset": 0,
  "limit": 20
}
```

### Process Batch
```http
POST /api/batches/{batch_id}/process
Content-Type: application/json

{
  "continue_on_error": true
}
```

### Reprocess Batch
```http
POST /api/batches/{batch_id}/reprocess
Content-Type: application/json

{
  "failed_items_only": true,
  "continue_on_error": true
}
```

**Response:**
```json
{
  "original_batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "new_batch_id": "660e8400-e29b-41d4-a716-446655440001",
  "items_to_reprocess": 5,
  "status": "completed",
  "message": "Batch reprocessed successfully"
}
```

### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "registered_batch_types": ["customer_data", "transaction_feed"]
}
```

## Custom Endpoint Behavior

While the auto-generated endpoints work great out of the box, you often need custom logic for:
- Validation rules
- Rate limiting
- Notifications
- Business logic
- Access control

### Convention-Based Customization

Just like processors, create a custom endpoint class:

```python
from reliable_imports import BaseEndpoint, EndpointContext
from reliable_imports.api_models import CreateBatchRequest

class CustomerDataEndpoint(BaseEndpoint):
    """
    Custom endpoint for customer_data batch type.

    Convention: CustomerDataEndpoint -> 'customer_data'
    """

    def before_create_batch(
        self, request_data: CreateBatchRequest, ctx: EndpointContext
    ) -> CreateBatchRequest:
        """Called before creating a batch."""
        # Custom validation
        if not self._check_quota(ctx.user_id):
            raise ValueError("Monthly quota exceeded")

        # Enrich data
        request_data.metadata = request_data.metadata or {}
        request_data.metadata['api_version'] = 'v1'

        return request_data

    def after_batch_complete(self, batch_id, summary, ctx: EndpointContext):
        """Called after batch processing completes."""
        # Send notification
        self._send_slack_notification(
            f"Batch {batch_id} completed with "
            f"{summary.success_rate}% success rate"
        )

        return {'notification_sent': True}
```

### Register Custom Endpoints

```python
# Auto-discovery
api_manager.endpoint_registry.discover('myapp.endpoints')

# Or manual registration
api_manager.endpoint_registry.register('customer_data', CustomerDataEndpoint)
```

## Lifecycle Hooks

Custom endpoints support these hooks:

### Before Hooks (Validation & Modification)

- `before_create_batch(request_data, ctx)` - Validate/modify batch creation
- `before_process_batch(batch_id, request_data, ctx)` - Validate processing
- `before_reprocess_batch(batch_id, request_data, ctx)` - Validate reprocessing

### After Hooks (Notifications & Side Effects)

- `after_create_batch(batch_id, request_data, ctx)` - Post-creation actions
- `after_batch_complete(batch_id, summary, ctx)` - Completion notifications
- `after_reprocess_complete(original_id, new_id, summary, ctx)` - Reprocess notifications

### Error Hooks

- `on_batch_error(batch_id, error, ctx)` - Handle processing failures

### Validation Helpers

- `validate_batch_access(batch_id, ctx)` - Access control
- `validate_create_batch_items(items, ctx)` - Custom item validation
- `check_rate_limit(ctx)` - Rate limiting
- `get_max_batch_size(ctx)` - Dynamic size limits

## Common Use Cases

### 1. Rate Limiting

```python
class CustomerDataEndpoint(BaseEndpoint):
    def check_rate_limit(self, ctx: EndpointContext) -> bool:
        # Check Redis or similar
        key = f"rate_limit:{ctx.user_id}"
        count = redis.incr(key)
        redis.expire(key, 3600)  # 1 hour window

        return count <= 100  # Max 100 requests per hour
```

### 2. Multi-Tenancy

```python
class CustomerDataEndpoint(BaseEndpoint):
    def before_create_batch(self, request_data, ctx):
        # Add tenant context
        request_data.metadata = request_data.metadata or {}
        request_data.metadata['tenant_id'] = ctx.user_id
        return request_data

    def validate_batch_access(self, batch_id, ctx):
        # Only allow access to own batches
        batch = self.ctx.batch_manager.get_batch_summary(batch_id)
        return batch.metadata.get('tenant_id') == ctx.user_id
```

### 3. Slack Notifications

```python
class CustomerDataEndpoint(BaseEndpoint):
    def after_batch_complete(self, batch_id, summary, ctx):
        if summary.failed_items > 0:
            self._send_slack_alert(
                f"⚠️ Batch {batch_id} had {summary.failed_items} failures"
            )
        else:
            self._send_slack_message(
                f"✅ Batch {batch_id} completed successfully"
            )
```

### 4. Email Domain Validation

```python
class CustomerDataEndpoint(BaseEndpoint):
    def validate_create_batch_items(self, items, ctx):
        errors = []
        allowed_domains = ['company.com', 'partner.com']

        for idx, item in enumerate(items):
            email = item.get('email', '')
            if '@' in email:
                domain = email.split('@')[1]
                if domain not in allowed_domains:
                    errors.append(
                        f"Item {idx}: Domain '{domain}' not allowed"
                    )

        return errors
```

### 5. Webhook Triggers

```python
class CustomerDataEndpoint(BaseEndpoint):
    def after_batch_complete(self, batch_id, summary, ctx):
        # Trigger downstream webhook
        webhook_url = ctx.request.headers.get('X-Webhook-URL')
        if webhook_url:
            requests.post(webhook_url, json={
                'batch_id': str(batch_id),
                'status': summary.status.value,
                'success_rate': summary.success_rate,
            })
```

## EndpointContext

The `EndpointContext` object provides access to:

```python
class EndpointContext:
    request: Request          # FastAPI request object
    batch_manager: BatchManager  # For database operations
    user_id: Optional[str]    # User ID (from auth)

    # Metadata storage
    def set_metadata(key: str, value: Any)
    def get_metadata(key: str, default=None) -> Any
```

## Authentication

To add authentication, extend the `APIManager`:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

def get_current_user(credentials = Depends(security)):
    # Validate JWT token
    token = credentials.credentials
    user = validate_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

# Override _create_endpoint_context to add user
class AuthAPIManager(APIManager):
    def _create_endpoint_context(self, request, user=Depends(get_current_user)):
        return EndpointContext(
            request=request,
            batch_manager=self.batch_manager,
            user_id=user.id,
        )
```

## Error Handling

The API automatically handles common errors:

| Exception | Status Code | Response |
|-----------|-------------|----------|
| `BatchNotFoundError` | 404 | `{"error": "BatchNotFoundError", "message": "..."}` |
| `ProcessorNotFoundError` | 400 | `{"error": "ProcessorNotFoundError", "message": "..."}` |
| `ValidationError` | 400 | `{"error": "ValidationError", "message": "..."}` |
| `HTTPException` | varies | FastAPI standard |

## Running in Production

### With Uvicorn Directly

```bash
uvicorn myapp.api:app --host 0.0.0.0 --port 8000 --workers 4
```

### With Gunicorn + Uvicorn Workers

```bash
gunicorn myapp.api:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "myapp.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Complete Example

See `examples/api_example.py` for a complete working example with:
- Processor implementation
- Custom endpoint with all hooks
- Server setup
- API client examples

Run it:
```bash
# Start server
python examples/api_example.py

# Test API (in another terminal)
python examples/api_example.py test
```

## Benefits Recap

✅ **15-20 hours saved** building REST APIs from scratch
✅ **Auto-generated OpenAPI docs** - no manual documentation needed
✅ **Type-safe** request/response with Pydantic
✅ **Convention-based** customization - minimal boilerplate
✅ **Production-ready** - comprehensive error handling, validation
✅ **Extensible** - easy to add auth, rate limiting, webhooks

## What's Next?

- Add authentication (JWT, OAuth, API keys)
- Implement rate limiting with Redis
- Add WebSocket support for real-time batch status
- Create GraphQL API layer
- Add batch scheduling endpoints

---

**Remember: Auto-generate by default, customize when needed.**

The framework provides sensible defaults while making it easy to add custom behavior exactly where you need it.
