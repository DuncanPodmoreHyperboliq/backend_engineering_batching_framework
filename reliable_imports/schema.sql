-- Reliable Imports Framework - Database Schema
-- This schema supports batch-based data ingestion with full reprocessing capabilities

-- Import batches track individual import operations
CREATE TABLE IF NOT EXISTS import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_type VARCHAR(100) NOT NULL,  -- Convention-based: e.g., 'customer_data', 'transaction_feed'
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, reprocessing
    source_info JSONB,  -- Metadata about data source (file path, API endpoint, etc.)
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    parent_batch_id UUID REFERENCES import_batches(id),  -- For reprocessing scenarios
    metadata JSONB DEFAULT '{}'::jsonb  -- Flexible metadata storage
);

-- Import batch items track individual records within a batch
CREATE TABLE IF NOT EXISTS import_batch_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    item_index INTEGER NOT NULL,  -- Order within batch
    status VARCHAR(50) NOT NULL DEFAULT 'pending',  -- pending, processing, completed, failed, skipped
    source_data JSONB NOT NULL,  -- Original data for reprocessing
    processed_data JSONB,  -- Transformed data
    target_table VARCHAR(100),  -- Convention-based target
    target_id UUID,  -- ID of created/updated record
    error_message TEXT,
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(batch_id, item_index)
);

-- Import logs provide detailed audit trail
CREATE TABLE IF NOT EXISTS import_logs (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    item_id UUID REFERENCES import_batch_items(id) ON DELETE CASCADE,
    log_level VARCHAR(20) NOT NULL,  -- debug, info, warning, error
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_import_batches_type_status ON import_batches(batch_type, status);
CREATE INDEX IF NOT EXISTS idx_import_batches_created ON import_batches(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_import_batches_parent ON import_batches(parent_batch_id);
CREATE INDEX IF NOT EXISTS idx_import_batch_items_batch ON import_batch_items(batch_id);
CREATE INDEX IF NOT EXISTS idx_import_batch_items_status ON import_batch_items(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_import_batch_items_target ON import_batch_items(target_table, target_id);
CREATE INDEX IF NOT EXISTS idx_import_logs_batch ON import_logs(batch_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_import_logs_item ON import_logs(item_id, created_at DESC);

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_import_batches_updated_at BEFORE UPDATE ON import_batches
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Helper views for common queries
CREATE OR REPLACE VIEW import_batch_summary AS
SELECT
    b.id,
    b.batch_type,
    b.status,
    b.created_at,
    b.started_at,
    b.completed_at,
    b.retry_count,
    COUNT(i.id) as total_items,
    COUNT(i.id) FILTER (WHERE i.status = 'completed') as completed_items,
    COUNT(i.id) FILTER (WHERE i.status = 'failed') as failed_items,
    COUNT(i.id) FILTER (WHERE i.status = 'pending') as pending_items,
    EXTRACT(EPOCH FROM (COALESCE(b.completed_at, NOW()) - b.started_at)) as duration_seconds
FROM import_batches b
LEFT JOIN import_batch_items i ON i.batch_id = b.id
GROUP BY b.id;

-- View for failed batches that need attention
CREATE OR REPLACE VIEW failed_imports_report AS
SELECT
    b.id,
    b.batch_type,
    b.created_at,
    b.error_message as batch_error,
    COUNT(i.id) FILTER (WHERE i.status = 'failed') as failed_items_count,
    b.retry_count
FROM import_batches b
LEFT JOIN import_batch_items i ON i.batch_id = b.id
WHERE b.status = 'failed'
GROUP BY b.id
ORDER BY b.created_at DESC;
