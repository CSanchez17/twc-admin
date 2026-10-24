-- One-shot backfill: per-language category display names (2026-10-25).
--
-- The blog_categories table (system of record: this panel) gained
-- name_en / name_de / name_es so the FastAPI app can show category labels
-- in the visitor's language (navbar dropdown, blog sidebar, category page,
-- post breadcrumbs). A NULL means "not translated" — the app falls back to
-- the base `name`.
--
-- First run: the ALTER adds the columns. Re-running later, the ALTER fails
-- with "Duplicate column name" (expected — ignore it); the UPDATEs below are
-- idempotent and keep the baseline labels in sync.
-- Apply against the shared DB:
--   docker exec -i twc-mysql sh -c 'mysql -utwc_user -p"$MYSQL_PASSWORD" --default-character-set=utf8mb4 twc' < scripts/backfill_category_names.sql
-- (on the host, or from inside the panel container with host rewritten)

ALTER TABLE blog_categories
  ADD COLUMN name_en VARCHAR(120) NULL,
  ADD COLUMN name_de VARCHAR(120) NULL,
  ADD COLUMN name_es VARCHAR(120) NULL;

-- Baseline: every language gets the base name (tech names are language-neutral).
UPDATE blog_categories SET name_en = name, name_de = name, name_es = name
  WHERE name_en IS NULL;

-- The three categories the site already translated (base.json c3-1/c3-2/c3-3)
-- keep their established localized labels.
UPDATE blog_categories SET name_en = 'General', name_de = 'Allgemein', name_es = 'General' WHERE id = 1;
UPDATE blog_categories SET name_en = 'Artificial-Intelligence', name_de = 'Künstliche-Intelligenz', name_es = 'Inteligencia-Artificial' WHERE id = 22;
UPDATE blog_categories SET name_en = 'Crypto-coins-and-Blockchain', name_de = 'Kryptowährungen-und-Blockchain', name_es = 'Criptomonedas-y-Blockchain' WHERE id = 23;
