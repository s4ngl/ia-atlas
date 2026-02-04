-- ============================================================================
-- ServiceNow Knowledge Base - Title-Based Deduplication (SAFE / RE-RUNNABLE)
-- ============================================================================
-- Deduplicates articles with the same title by keeping the best canonical
-- version and merging links + metadata.
-- ============================================================================

\set ON_ERROR_STOP on

BEGIN;

\echo '========================================='
\echo 'Title-Based Deduplication'
\echo '========================================='

-- --------------------------------------------------------------------------
-- Step 0: Clean up temp tables if script was run before in this session
-- --------------------------------------------------------------------------

DROP TABLE IF EXISTS canonical_by_title;
DROP TABLE IF EXISTS title_mapping;
DROP TABLE IF EXISTS title_updated_links;

-- --------------------------------------------------------------------------
-- Step 1: Identify duplicate titles
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 1: Analyzing duplicate titles...'

SELECT
    COUNT(*) AS title_groups_with_duplicates,
    SUM(duplicate_count - 1) AS total_duplicates_to_remove
FROM (
    SELECT title, COUNT(*) AS duplicate_count
    FROM articles
    WHERE title IS NOT NULL
      AND title != ''
      AND title != 'Pending'
    GROUP BY title
    HAVING COUNT(*) > 1
) dupes;

\echo ''
\echo 'Top 10 most duplicated titles:'

SELECT
    title,
    COUNT(*) AS duplicate_count
FROM articles
WHERE title IS NOT NULL
  AND title != ''
  AND title != 'Pending'
GROUP BY title
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 10;

-- --------------------------------------------------------------------------
-- Step 2: Select canonical article per title
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 2: Selecting canonical version for each title...'

CREATE TEMP TABLE canonical_by_title AS
SELECT DISTINCT ON (title)
    title,
    id AS canonical_id
FROM articles
WHERE title IS NOT NULL
  AND title != ''
  AND title != 'Pending'
ORDER BY
    title,
    -- Deprioritize outdated / archived
    CASE
        WHEN LOWER(title) LIKE '%outdated%' THEN 2
        WHEN LOWER(title) LIKE '%archived%' THEN 2
        ELSE 0
    END,
    -- Prefer articles with content
    CASE
        WHEN content IS NOT NULL AND LENGTH(content) > 0 THEN 0
        ELSE 1
    END,
    -- Prefer most recently updated
    updated_at DESC NULLS LAST,
    crawled_at DESC NULLS LAST,
    -- Fallback: higher ID
    id DESC;

SELECT COUNT(*) AS canonical_articles_by_title
FROM canonical_by_title;

-- --------------------------------------------------------------------------
-- Step 3: Map duplicate IDs → canonical IDs
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 3: Creating title-based mapping...'

CREATE TEMP TABLE title_mapping AS
SELECT
    a.id AS old_id,
    c.canonical_id AS new_id
FROM articles a
JOIN canonical_by_title c
  ON a.title = c.title
WHERE a.id != c.canonical_id
  AND a.title IS NOT NULL
  AND a.title != ''
  AND a.title != 'Pending';

SELECT COUNT(*) AS articles_to_merge_by_title
FROM title_mapping;

-- --------------------------------------------------------------------------
-- Step 4: Update links to point to canonical articles
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 4: Updating links to canonical versions...'

CREATE TEMP TABLE title_updated_links AS
SELECT DISTINCT
    COALESCE(m1.new_id, l.source_id) AS source_id,
    COALESCE(m2.new_id, l.target_id) AS target_id,
    MIN(l.created_at) AS created_at
FROM links l
LEFT JOIN title_mapping m1 ON l.source_id = m1.old_id
LEFT JOIN title_mapping m2 ON l.target_id = m2.old_id
GROUP BY
    COALESCE(m1.new_id, l.source_id),
    COALESCE(m2.new_id, l.target_id);

SELECT COUNT(*) AS links_before FROM links;

DELETE FROM links;

INSERT INTO links (source_id, target_id, created_at)
SELECT source_id, target_id, created_at
FROM title_updated_links;

SELECT COUNT(*) AS links_after FROM links;

-- --------------------------------------------------------------------------
-- Step 5: Merge best data into canonical articles
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 5: Merging data into canonical articles...'

UPDATE articles a
SET
    content = COALESCE(
        a.content,
        (
            SELECT content
            FROM articles a2
            WHERE a2.title = a.title
              AND a2.content IS NOT NULL
              AND LENGTH(a2.content) > COALESCE(LENGTH(a.content), 0)
            ORDER BY LENGTH(a2.content) DESC, a2.updated_at DESC
            LIMIT 1
        ),
        a.content
    ),
    number = COALESCE(
        NULLIF(a.number, ''),
        (
            SELECT number
            FROM articles a2
            WHERE a2.title = a.title
              AND a2.number IS NOT NULL
              AND a2.number != ''
            ORDER BY a2.updated_at DESC
            LIMIT 1
        ),
        a.number
    ),
    display_number = COALESCE(
        NULLIF(a.display_number, ''),
        (
            SELECT display_number
            FROM articles a2
            WHERE a2.title = a.title
              AND a2.display_number IS NOT NULL
              AND a2.display_number != ''
            ORDER BY a2.updated_at DESC
            LIMIT 1
        ),
        a.display_number
    )
WHERE a.id IN (
    SELECT canonical_id FROM canonical_by_title
);

\echo 'Data merged into canonical articles'

-- --------------------------------------------------------------------------
-- Step 6: Delete duplicate versions
-- --------------------------------------------------------------------------

\echo ''
\echo 'Step 6: Deleting duplicate versions...'

SELECT COUNT(*) AS articles_before_deletion FROM articles;

DELETE FROM articles
WHERE id IN (SELECT old_id FROM title_mapping);

SELECT COUNT(*) AS articles_after_deletion FROM articles;

-- --------------------------------------------------------------------------
-- Step 7: Final statistics
-- --------------------------------------------------------------------------

\echo ''
\echo '========================================='
\echo 'Title-Based Deduplication Complete!'
\echo '========================================='

SELECT
    COUNT(*) AS total_articles,
    COUNT(CASE WHEN content IS NOT NULL AND content != '' THEN 1 END) AS crawled_articles,
    COUNT(CASE WHEN title = 'Pending' THEN 1 END) AS pending_stubs,
    COUNT(DISTINCT NULLIF(title, 'Pending')) AS unique_titles
FROM articles;

\echo ''
SELECT COUNT(*) AS total_links FROM links;

\echo ''
\echo 'Checking for remaining title duplicates...'

SELECT title, COUNT(*) AS count
FROM articles
WHERE title IS NOT NULL
  AND title != ''
  AND title != 'Pending'
GROUP BY title
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 5;

\echo ''
\echo 'If no rows above, title deduplication was successful!'
\echo '========================================='

COMMIT;
