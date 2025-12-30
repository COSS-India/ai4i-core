-- PostgreSQL 12 Compatibility Fix for Konga
-- This script adds compatibility views for columns removed in PostgreSQL 12
-- that Konga's older ORM still expects

-- Create compatibility view for pg_constraint.consrc
-- The consrc column was removed in PostgreSQL 12
CREATE OR REPLACE VIEW pg_constraint_compat AS
SELECT 
    c.*,
    CASE 
        WHEN c.contype = 'c' THEN
            pg_get_constraintdef(c.oid)
        ELSE
            NULL::text
    END AS consrc
FROM pg_constraint c;

-- Grant access to the view
GRANT SELECT ON pg_constraint_compat TO PUBLIC;

-- Create a trigger function to redirect queries from pg_constraint to the compatibility view
-- This is a workaround for applications querying pg_constraint.consrc directly

-- Note: We can't create a view with the same name as a table, so we'll create a function
-- that can be used by applications, or modify the default search path
-- However, the simplest approach is to patch the database at runtime

COMMENT ON VIEW pg_constraint_compat IS 'Compatibility view for PostgreSQL 12 - provides consrc column for Konga';


