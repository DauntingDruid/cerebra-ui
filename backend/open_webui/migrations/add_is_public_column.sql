-- Migration: Add is_public column to enable resource sharing
-- Date: 2025-01-09
-- Author: Sadman Ali
-- Depends on: add_workflow_tables.sql

-- Add is_public column to workflows table
ALTER TABLE workflows ADD COLUMN is_public BOOLEAN DEFAULT 0;

-- Add is_public column to model table  
ALTER TABLE model ADD COLUMN is_public BOOLEAN DEFAULT 0;

-- Set all existing admin resources to public
-- This allows regular users to see admin-created models and workflows
UPDATE workflows 
SET is_public = 1 
WHERE user_id IN (SELECT id FROM user WHERE role = 'admin');

UPDATE model 
SET is_public = 1 
WHERE user_id IN (SELECT id FROM user WHERE role = 'admin');

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_workflows_is_public ON workflows(is_public);
CREATE INDEX IF NOT EXISTS idx_model_is_public ON model(is_public);

-- Verify migration
SELECT 'Workflows updated:' as info, COUNT(*) as count FROM workflows WHERE is_public = 1;
SELECT 'Models updated:' as info, COUNT(*) as count FROM model WHERE is_public = 1;