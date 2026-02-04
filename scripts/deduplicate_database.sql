-- ============================================================================
-- ServiceNow Knowledge Base - Database Deduplication Script (Fixed)
-- ============================================================================

BEGIN;

-- Step 1: Create a function to extract sys_kb_id from URL
-- ============================================================================
CREATE OR REPLACE FUNCTION extract_sys_kb_id(url TEXT) RETURNS TEXT AS $$
DECLARE
    kb_id TEXT;
BEGIN
    -- Try to extract sys_kb_id parameter from URL
    kb_id := (regexp_matches(url, 'sys_kb_id=([a-f0-9]+)', 'i'))[1];

    IF kb_id IS NOT NULL THEN
        RETURN kb_id;
    END IF;

    -- Try to extract sysparm_article parameter (KB number format)
    kb_id := (regexp_matches(url, 'sysparm_article=(KB[0-9]+)', 'i'))[1];

    IF kb_id IS NOT NULL THEN
        RETURN kb_id;
    END IF;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Step 2: Add a column to store the canonical sys_kb_id
-- ============================================================================
ALTER TABLE articles ADD COLUMN IF NOT EXISTS sys_kb_id TEXT;

-- Populate sys_kb_id for all articles
UPDATE articles SET sys_kb_id = extract_sys_kb_id(url);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_articles_sys_kb_id ON articles(sys_kb_id);

-- Step 3: Identify and log duplicates
-- ============================================================================
DO $$
DECLARE
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT sys_kb_id
        FROM articles
        WHERE sys_kb_id IS NOT NULL
        GROUP BY sys_kb_id
        HAVING COUNT(*) > 1
    ) AS dupes;

    RAISE NOTICE 'Found % article groups with duplicates', duplicate_count;
END $$;

-- Show top duplicates (for verification)
SELECT
    sys_kb_id,
    COUNT(*) as duplicate_count,
    MIN(title) as title
FROM articles
WHERE sys_kb_id IS NOT NULL
GROUP BY sys_kb_id
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 10;

-- Step 4: Create temporary table with canonical article IDs
-- ============================================================================
CREATE TEMP TABLE canonical_articles AS
SELECT DISTINCT ON (sys_kb_id)
    sys_kb_id,
    id as canonical_id
FROM articles
WHERE sys_kb_id IS NOT NULL
ORDER BY sys_kb_id,
    -- Prefer articles with content
    CASE WHEN content IS NOT NULL AND content != '' THEN 0 ELSE 1 END,
    -- Prefer articles with more complete data
    CASE WHEN title != 'Pending' THEN 0 ELSE 1 END,
    -- Prefer earlier IDs (likely original entries)
    id ASC;

-- Show how many canonical articles we identified
SELECT COUNT(*) as canonical_articles FROM canonical_articles;

-- Step 5: Create mapping from duplicate IDs to canonical IDs
-- ============================================================================
CREATE TEMP TABLE id_mapping AS
SELECT
    a.id as old_id,
    c.canonical_id as new_id
FROM articles a
JOIN canonical_articles c ON a.sys_kb_id = c.sys_kb_id
WHERE a.id != c.canonical_id;

-- Show how many articles will be merged
SELECT COUNT(*) as articles_to_merge FROM id_mapping;

-- Step 6: FIRST remove duplicate links, THEN update references
-- ============================================================================

-- Create temp table with all links that need to be updated
CREATE TEMP TABLE updated_links AS
SELECT DISTINCT
    COALESCE(m1.new_id, l.source_id) as source_id,
    COALESCE(m2.new_id, l.target_id) as target_id,
    MIN(l.created_at) as created_at
FROM links l
LEFT JOIN id_mapping m1 ON l.source_id = m1.old_id
LEFT JOIN id_mapping m2 ON l.target_id = m2.old_id
GROUP BY
    COALESCE(m1.new_id, l.source_id),
    COALESCE(m2.new_id, l.target_id);

-- Delete all existing links
DELETE FROM links;

-- Reinsert with updated IDs (now deduplicated)
INSERT INTO links (source_id, target_id, created_at)
SELECT source_id, target_id, created_at
FROM updated_links;

-- Step 7: Merge article data (keep best data from duplicates)
-- ============================================================================

-- Update canonical articles with best available data
UPDATE articles a
SET
    title = COALESCE(
        NULLIF(a.title, 'Pending'),
        (SELECT title FROM articles WHERE sys_kb_id = a.sys_kb_id AND title != 'Pending' ORDER BY id LIMIT 1),
        a.title
    ),
    content = COALESCE(
        NULLIF(a.content, ''),
        (SELECT content FROM articles WHERE sys_kb_id = a.sys_kb_id AND content IS NOT NULL AND content != '' ORDER BY id LIMIT 1),
        a.content
    ),
    number = COALESCE(
        NULLIF(a.number, ''),
        (SELECT number FROM articles WHERE sys_kb_id = a.sys_kb_id AND number IS NOT NULL AND number != '' ORDER BY id LIMIT 1),
        a.number
    ),
    display_number = COALESCE(
        NULLIF(a.display_number, ''),
        (SELECT display_number FROM articles WHERE sys_kb_id = a.sys_kb_id AND display_number IS NOT NULL AND display_number != '' ORDER BY id LIMIT 1),
        a.display_number
    ),
    snippet = COALESCE(
        NULLIF(a.snippet, ''),
        (SELECT snippet FROM articles WHERE sys_kb_id = a.sys_kb_id AND snippet IS NOT NULL AND snippet != '' ORDER BY id LIMIT 1),
        a.snippet
    )
WHERE a.id IN (SELECT canonical_id FROM canonical_articles);

-- Step 8: Delete duplicate articles
-- ============================================================================

DELETE FROM articles
WHERE id IN (SELECT old_id FROM id_mapping);

-- Step 9: Final statistics
-- ============================================================================
DO $$
DECLARE
    total_articles INTEGER;
    crawled_articles INTEGER;
    pending_articles INTEGER;
    total_links INTEGER;
    unique_kb_ids INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_articles FROM articles;
    SELECT COUNT(*) INTO crawled_articles FROM articles WHERE content IS NOT NULL AND content != '';
    SELECT COUNT(*) INTO pending_articles FROM articles WHERE title = 'Pending';
    SELECT COUNT(*) INTO total_links FROM links;
    SELECT COUNT(DISTINCT sys_kb_id) INTO unique_kb_ids FROM articles WHERE sys_kb_id IS NOT NULL;

    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Deduplication Complete!';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Total articles:        %', total_articles;
    RAISE NOTICE 'Crawled articles:      %', crawled_articles;
    RAISE NOTICE 'Pending stubs:         %', pending_articles;
    RAISE NOTICE 'Total links:           %', total_links;
    RAISE NOTICE 'Unique KB IDs:         %', unique_kb_ids;
    RAISE NOTICE '========================================';
END $$;

-- Verify no duplicates remain
SELECT
    sys_kb_id,
    COUNT(*) as count
FROM articles
WHERE sys_kb_id IS NOT NULL
GROUP BY sys_kb_id
HAVING COUNT(*) > 1;

COMMIT;

-- Post-commit: Add unique constraint
-- ============================================================================
ALTER TABLE articles ADD CONSTRAINT unique_sys_kb_id UNIQUE (sys_kb_id);

SELECT 'Deduplication complete! Added UNIQUE constraint on sys_kb_id.' as status;
