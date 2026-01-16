-- Migration: Add figure reference support to image_embeddings
-- Description: Stores figure reference labels (図1.1, Figure 1.1, etc.) with extracted images

-- Add figure_reference column for reference labels like "図1.1", "Figure 1-1"
ALTER TABLE image_embeddings ADD COLUMN IF NOT EXISTS figure_reference VARCHAR(100);

-- Add figure_caption column for caption text near the figure
ALTER TABLE image_embeddings ADD COLUMN IF NOT EXISTS figure_caption TEXT;

-- Index for fast figure reference lookup by document
CREATE INDEX IF NOT EXISTS idx_image_embeddings_figure_ref
ON image_embeddings(document_id, figure_reference)
WHERE figure_reference IS NOT NULL;

-- Comment for documentation
COMMENT ON COLUMN image_embeddings.figure_reference IS 'Figure reference label extracted from document (e.g., 図1.1, Figure 1-1)';
COMMENT ON COLUMN image_embeddings.figure_caption IS 'Caption text associated with the figure';
