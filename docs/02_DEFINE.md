# Double Diamond: Define Phase

## Overview

The Define phase synthesizes the insights from the Discover phase into a clear problem statement, requirements, and design principles. This phase narrows from broad exploration to focused definition.

## Problem Statement

**Small engineering teams waste 40-60 hours per import pipeline building custom batch tracking, error handling, and reprocessing logic, when they should be focusing on business logic. This developer time drain compounds as more import types are added, creating unsustainable technical debt.**

### Problem Breakdown

#### Core Problem
Developer time (the scarcest resource) is consumed by infrastructure boilerplate rather than business value.

#### Contributing Factors
1. No standard framework for small team data ingestion
2. Each import requires rebuilding batch tracking
3. Error handling logic is duplicated across imports
4. Reprocessing failures is manual and time-consuming
5. Limited audit trails make debugging difficult
6. Lack of conventions leads to inconsistent implementations

#### Impact
- 40-60 hours per import pipeline (initial development)
- 5-10 hours per week debugging data issues
- 2-3 hours per failed import incident
- Increasing technical debt as team grows
- Delayed feature development
- Developer frustration and burnout

## Design Principles

Based on the Discover phase findings, the framework must adhere to these principles:

### 1. Developer Time is the Primary Metric
**Every design decision should optimize for developer time saved.**
- Choose simplicity over completeness
- Minimize boilerplate over maximum flexibility
- Reduce decisions over maximum customization

### 2. Convention Over Configuration
**Reduce cognitive load through sensible defaults and naming conventions.**
- Auto-discovery based on class names
- Standard patterns for common operations
- Minimal required configuration

### 3. PostgreSQL-Native
**Work with existing infrastructure, don't add new dependencies.**
- Use PostgreSQL for all persistence
- Leverage PostgreSQL features (JSONB, UUIDs, transactions)
- No message queues, caches, or external services required

### 4. Reliability by Default
**Make the right thing the easy thing.**
- Automatic transaction management
- Built-in error handling
- Comprehensive audit trails
- Idempotent operations

### 5. Easy Reprocessing
**Failed imports should be fixable in minutes, not hours.**
- Store original source data
- One-command reprocessing
- Selective reprocessing (failed items only)

### 6. Progressive Disclosure
**Simple cases should be simple; complex cases should be possible.**
- Sensible defaults for common cases
- Escape hatches for custom requirements
- Hooks for advanced customization

## Requirements

### Functional Requirements

#### Must Have (P0)
1. **Batch Creation**
   - Create batch with collection of items
   - Assign unique batch ID (UUID)
   - Store source data for each item
   - Support metadata storage

2. **Batch Processing**
   - Process items sequentially
   - Wrap in transactions
   - Track item-level status
   - Continue on error (configurable)

3. **Processor System**
   - Base class for custom processors
   - Convention-based registration
   - Validation hooks
   - Processing hooks

4. **Status Tracking**
   - Batch status (pending, processing, completed, failed)
   - Item status (pending, processing, completed, failed, skipped)
   - Timestamps for all state changes

5. **Error Handling**
   - Capture errors at item level
   - Store error messages
   - Continue processing after errors
   - Automatic rollback on transaction failures

6. **Reprocessing**
   - Reprocess entire batch
   - Reprocess failed items only
   - Link to original batch
   - Preserve source data

7. **Logging**
   - Item-level logging
   - Batch-level logging
   - Structured log data
   - Log levels (debug, info, warning, error)

8. **Context API**
   - Database connection access
   - Logging helpers
   - Common query helpers
   - Metadata storage

#### Should Have (P1)
1. **Batch Summary**
   - Success/failure counts
   - Processing duration
   - Throughput metrics

2. **Processor Discovery**
   - Auto-discover processors in package
   - Register by convention

3. **Query Views**
   - Summary view for monitoring
   - Failed batches view

4. **Hooks**
   - on_batch_start
   - on_batch_complete
   - on_item_error

#### Could Have (P2)
1. Retry logic with backoff
2. Parallel processing of items
3. Batch dependencies
4. Progress callbacks
5. Metrics/monitoring integration

#### Won't Have (Out of Scope)
1. Scheduling/orchestration
2. Distributed processing
3. Real-time streaming
4. Data transformation DSL
5. UI/dashboard
6. Multi-database support

### Non-Functional Requirements

#### Performance
- Process 1000 items in < 5 minutes (for simple operations)
- Batch creation in < 1 second
- Status queries in < 100ms

#### Reliability
- ACID transactions for each item
- No data loss on failures
- Graceful handling of partial failures

#### Usability
- < 1 hour to setup and first import
- < 4 hours to build a production import pipeline
- Clear error messages
- Good documentation with examples

#### Maintainability
- < 2000 lines of core framework code
- Minimal dependencies (just psycopg2)
- Clear separation of concerns
- Well-tested core functionality

## System Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────┐
│                     BatchManager                         │
│                                                          │
│  - Orchestrates batch lifecycle                         │
│  - Manages transactions                                  │
│  - Coordinates with registry and processors              │
└─────────────┬───────────────────────────────────────────┘
              │
              ├──────────────────┬──────────────────┬──────────────────
              │                  │                  │
        ┌─────▼─────┐      ┌────▼────┐       ┌────▼──────┐
        │ Registry  │      │ Context │       │ Database  │
        └─────┬─────┘      └────┬────┘       └────┬──────┘
              │                 │                  │
              │                 │                  │
        ┌─────▼───────────────────────┐    ┌──────▼───────────┐
        │ User-Defined Processors     │    │  Schema Tables   │
        │                             │    │  - batches       │
        │  - CustomerDataProcessor    │    │  - items         │
        │  - TransactionProcessor     │    │  - logs          │
        │  - ProductProcessor         │    │                  │
        └─────────────────────────────┘    └──────────────────┘
```

### Core Classes

#### 1. BatchManager
**Responsibility**: Orchestrate batch operations
**Key Methods**:
- `create_batch(batch_type, items, metadata)`
- `process_batch(batch_id)`
- `reprocess_batch(batch_id, failed_only)`
- `get_batch_summary(batch_id)`

#### 2. BaseProcessor (Abstract)
**Responsibility**: Define processing interface
**Key Methods**:
- `validate_batch(ctx)` - Batch-level validation
- `validate_item(item, ctx)` - Item-level validation
- `process_item(item, ctx)` - Main processing logic
- `on_batch_start(ctx)` - Setup hook
- `on_batch_complete(ctx, success)` - Cleanup hook
- `on_item_error(item, error, ctx)` - Error handling hook

#### 3. ImportContext
**Responsibility**: Provide processing environment
**Key Methods**:
- `execute(query, params)` - Run queries
- `log(level, message, details)` - Logging
- `info/warning/error()` - Convenience logging
- `set_metadata/get_metadata()` - Context data

#### 4. ProcessorRegistry
**Responsibility**: Manage processor registration
**Key Methods**:
- `register(batch_type, processor_class)` - Manual registration
- `get(batch_type)` - Retrieve processor
- `discover(package)` - Auto-discover processors

#### 5. Models
**ImportBatch**: Batch metadata and status
**ImportBatchItem**: Individual item within batch
**BatchSummary**: Aggregated statistics

### Database Schema

#### import_batches
- `id` (UUID, PK)
- `batch_type` (VARCHAR)
- `status` (VARCHAR)
- `source_info` (JSONB)
- `metadata` (JSONB)
- `started_at`, `completed_at`
- `error_message` (TEXT)
- `retry_count` (INT)
- `parent_batch_id` (UUID, FK to self)

#### import_batch_items
- `id` (UUID, PK)
- `batch_id` (UUID, FK)
- `item_index` (INT)
- `status` (VARCHAR)
- `source_data` (JSONB) - **Critical for reprocessing**
- `processed_data` (JSONB)
- `target_table` (VARCHAR)
- `target_id` (UUID)
- `error_message` (TEXT)

#### import_logs
- `id` (BIGSERIAL, PK)
- `batch_id` (UUID, FK)
- `item_id` (UUID, FK, nullable)
- `log_level` (VARCHAR)
- `message` (TEXT)
- `details` (JSONB)
- `created_at` (TIMESTAMP)

### Convention System

#### Processor Naming Convention
```
Class Name Pattern: <BatchType>Processor (PascalCase)
Batch Type: <batch_type> (snake_case)

Examples:
- CustomerDataProcessor → batch_type = "customer_data"
- TransactionFeedProcessor → batch_type = "transaction_feed"
- ProductCatalogProcessor → batch_type = "product_catalog"
```

#### Auto-Discovery Pattern
```python
# Framework auto-discovers processors in a package
manager.registry.discover('myapp.processors')

# Automatically finds and registers:
# - myapp.processors.customer.CustomerDataProcessor
# - myapp.processors.transactions.TransactionFeedProcessor
# - etc.
```

#### Return Value Convention
```python
def process_item(self, item, ctx):
    # ... processing logic ...

    return {
        'target_table': 'customers',  # Optional: table affected
        'target_id': customer_id,      # Optional: record ID
        'processed_data': {...},       # Optional: transformed data
        # ... any other metadata ...
    }
```

## User Workflows

### Workflow 1: Create New Import Pipeline

**Goal**: Developer needs to import customer data from CSV

**Steps**:
1. Create processor class following convention
2. Implement `validate_item()` method
3. Implement `process_item()` method
4. Run discovery to register processor
5. Call `create_batch()` and `process_batch()`

**Time**: 2-4 hours (vs. 40-60 hours custom)

### Workflow 2: Handle Failed Import

**Goal**: 50 out of 1000 items failed, need to reprocess

**Steps**:
1. Check batch summary to see failures
2. Review logs to understand errors
3. Fix underlying issue (if needed)
4. Call `reprocess_batch(batch_id, failed_items_only=True)`

**Time**: 15-30 minutes (vs. 2-3 hours manual)

### Workflow 3: Add New Import Type

**Goal**: Add transaction import to existing system

**Steps**:
1. Create `TransactionFeedProcessor` class
2. Implement validation and processing logic
3. Framework automatically registers on discovery

**Time**: 1-2 hours (vs. 8-12 hours if rebuilding infrastructure)

## Key Decisions

### Decision 1: PostgreSQL-Only vs. Database Abstraction
**Choice**: PostgreSQL-only
**Rationale**:
- Target audience already uses PostgreSQL
- Abstraction adds complexity without benefit
- Can leverage PostgreSQL-specific features
- Reduces code and dependencies

### Decision 2: Synchronous vs. Async Processing
**Choice**: Synchronous (with optional background future enhancement)
**Rationale**:
- Simpler mental model
- Easier debugging
- Most small teams process < 10K items per batch
- Can add async later if needed

### Decision 3: Convention-Based vs. Explicit Registration
**Choice**: Both (convention preferred, explicit available)
**Rationale**:
- Convention reduces boilerplate (80% case)
- Explicit registration available for edge cases
- Developer can choose based on preference

### Decision 4: Store Source Data vs. Reference Original
**Choice**: Store source data in items table
**Rationale**:
- **Critical for easy reprocessing**
- Source data may change or be deleted
- JSONB storage is efficient enough for small batches
- Tradeoff storage for reliability and convenience

### Decision 5: Item-Level Transactions vs. Batch Transaction
**Choice**: Item-level transactions
**Rationale**:
- Allows partial batch success
- Better fault isolation
- Can reprocess only failed items
- More resilient to transient failures

## Success Criteria

### Primary Success Criterion
**Developer Time Saved**: Framework users spend 70% less time on data infrastructure

**Measurement**:
- Before: 40-60 hours for first import, 8-12 hours for additional
- After: 2-4 hours for first import, 1-2 hours for additional

### Secondary Success Criteria

1. **Adoption Rate**: 80%+ of new imports use framework
2. **Time to First Import**: < 1 hour setup + < 4 hours implementation
3. **Reprocessing Time**: < 30 minutes to reprocess failed batch
4. **Developer Satisfaction**: Positive feedback from team

## Constraints & Limitations

### Technical Constraints
- PostgreSQL 12+ required (for `gen_random_uuid()`)
- Python 3.7+ required
- Single database instance (no distributed)
- Maximum ~1M items per batch (performance target)

### Scope Limitations
- Not a workflow orchestrator (use Airflow if needed)
- Not for real-time streaming (use Kafka if needed)
- Not for analytics processing (use dbt if needed)
- No built-in scheduling (use cron if needed)

### Acceptable Tradeoffs
- Some storage overhead (storing source data) for reprocessing convenience
- Synchronous processing for simplicity (can add async later)
- PostgreSQL-only for reduced complexity
- Convention-based for reduced boilerplate (with escape hatches)

## Risks & Mitigations

### Risk 1: Framework Too Opinionated
**Impact**: Developers can't implement needed customization
**Mitigation**:
- Provide hooks at key points
- Allow manual registration
- Make base classes easy to extend

### Risk 2: Performance Bottlenecks
**Impact**: Framework too slow for real use cases
**Mitigation**:
- Optimize database queries
- Add indexes
- Document performance characteristics
- Async processing in future if needed

### Risk 3: Maintenance Burden
**Impact**: Framework becomes another thing to maintain
**Mitigation**:
- Keep code simple (< 2000 LOC)
- Minimal dependencies
- Good test coverage
- Clear documentation

### Risk 4: Adoption Resistance
**Impact**: Team prefers custom scripts
**Mitigation**:
- Make framework easier than custom code
- Provide clear examples
- Show time savings metrics
- Make incremental adoption possible

## Definition of Done

The Define phase is complete when we have:

✅ Clear problem statement
✅ Design principles established
✅ Requirements prioritized (must/should/could/won't have)
✅ Architecture designed
✅ Key decisions documented
✅ Success criteria defined
✅ Risks identified and mitigated

## Next Steps

Move to the **Develop** phase to:
1. Implement the core framework
2. Build example processors
3. Create documentation
4. Develop tests
5. Validate design decisions

**Key Question for Develop**: Does the implementation deliver the time savings we've defined as success?
