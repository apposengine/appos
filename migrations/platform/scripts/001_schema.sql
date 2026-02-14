-- ============================================================================
-- AppOS Platform Database — 001: Schema Creation
-- ============================================================================
-- Purpose:  Create the "appOS" schema for all platform objects.
-- Source:   AppOS_Database_Design.md v1.0, §2
-- Run:      First script in sequence
-- Idempotent: Yes (IF NOT EXISTS)
-- ============================================================================

-- Create the appOS schema (all platform tables live here, never in public)
CREATE SCHEMA IF NOT EXISTS "appOS";

-- Set search path for this session
SET search_path TO "appOS", public;

-- Confirm
DO $$
BEGIN
    RAISE NOTICE 'Schema "appOS" created/verified successfully.';
END $$;
