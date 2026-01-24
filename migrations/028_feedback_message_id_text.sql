-- Migration: 028_feedback_message_id_text.sql
-- Description: Change message_id from UUID to TEXT to support client-generated IDs
-- Reason: Frontend generates message IDs like 'msg-1706123456789-assistant'

-- ============================================
-- 1. Drop dependent views and triggers first
-- ============================================

DROP VIEW IF EXISTS v_feedback_summary CASCADE;
DROP VIEW IF EXISTS v_daily_feedback_stats CASCADE;
DROP TRIGGER IF EXISTS trigger_auto_register_verified_knowledge ON user_feedbacks;

-- ============================================
-- 2. Alter user_feedbacks table
-- ============================================

-- Drop the index first
DROP INDEX IF EXISTS idx_user_feedbacks_message_id;

-- Change column types
ALTER TABLE user_feedbacks
    ALTER COLUMN message_id TYPE TEXT USING message_id::TEXT,
    ALTER COLUMN conversation_id DROP NOT NULL,
    ALTER COLUMN conversation_id TYPE TEXT USING conversation_id::TEXT;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_user_feedbacks_message_id ON user_feedbacks(message_id);

-- ============================================
-- 3. Alter citation_feedbacks table
-- ============================================

-- Drop the index first
DROP INDEX IF EXISTS idx_citation_feedbacks_message_id;

-- Change column type
ALTER TABLE citation_feedbacks
    ALTER COLUMN message_id TYPE TEXT USING message_id::TEXT;

-- Recreate index
CREATE INDEX IF NOT EXISTS idx_citation_feedbacks_message_id ON citation_feedbacks(message_id);

-- ============================================
-- 4. Alter verified_knowledge table
-- ============================================

ALTER TABLE verified_knowledge
    ALTER COLUMN message_id TYPE TEXT USING message_id::TEXT,
    ALTER COLUMN conversation_id DROP NOT NULL,
    ALTER COLUMN conversation_id TYPE TEXT USING conversation_id::TEXT;

-- ============================================
-- 5. Recreate the views
-- ============================================

CREATE OR REPLACE VIEW v_feedback_summary AS
SELECT
    message_id,
    conversation_id,
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up_count,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down_count,
    ROUND(
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as positive_ratio,
    jsonb_agg(DISTINCT categories) FILTER (WHERE categories != '[]') as all_categories
FROM user_feedbacks
GROUP BY message_id, conversation_id;

CREATE OR REPLACE VIEW v_daily_feedback_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_feedbacks,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up') as thumbs_up,
    COUNT(*) FILTER (WHERE feedback_type = 'thumbs_down') as thumbs_down,
    ROUND(
        COUNT(*) FILTER (WHERE feedback_type = 'thumbs_up')::NUMERIC /
        NULLIF(COUNT(*), 0) * 100,
        2
    ) as satisfaction_rate,
    COUNT(DISTINCT user_id) as unique_users,
    COUNT(DISTINCT conversation_id) as unique_conversations
FROM user_feedbacks
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================
-- 6. Recreate the trigger function (without UUID cast)
-- ============================================

CREATE OR REPLACE FUNCTION auto_register_verified_knowledge()
RETURNS TRIGGER AS $$
DECLARE
    v_question TEXT;
    v_answer TEXT;
    v_sources JSONB;
    v_existing_count INT;
BEGIN
    -- 👍 피드백인 경우에만 처리
    IF NEW.feedback_type = 'thumbs_up' THEN
        -- 이미 등록되어 있는지 확인
        SELECT COUNT(*) INTO v_existing_count
        FROM verified_knowledge
        WHERE message_id = NEW.message_id;

        IF v_existing_count = 0 THEN
            -- 새로 등록
            INSERT INTO verified_knowledge (
                message_id,
                conversation_id,
                user_id,
                question,
                answer,
                source_documents,
                feedback_score,
                thumbs_up_count,
                status
            )
            VALUES (
                NEW.message_id,
                NEW.conversation_id,
                NEW.user_id,
                COALESCE(NEW.query_snapshot, ''),
                COALESCE(NEW.answer_snapshot, ''),
                COALESCE(NEW.sources_snapshot, '[]'::JSONB),
                1.0,
                1,
                'active'
            )
            ON CONFLICT (message_id) DO UPDATE SET
                thumbs_up_count = verified_knowledge.thumbs_up_count + 1,
                feedback_score = (verified_knowledge.thumbs_up_count + 1)::FLOAT /
                    NULLIF(verified_knowledge.thumbs_up_count + 1 + verified_knowledge.thumbs_down_count, 0),
                updated_at = NOW();

            RAISE NOTICE '[VerifiedKnowledge] Auto-registered from thumbs_up feedback: message_id=%', NEW.message_id;
        ELSE
            -- 기존 항목 업데이트
            UPDATE verified_knowledge
            SET
                thumbs_up_count = thumbs_up_count + 1,
                feedback_score = (thumbs_up_count + 1)::FLOAT /
                    NULLIF(thumbs_up_count + 1 + thumbs_down_count, 0),
                updated_at = NOW()
            WHERE message_id = NEW.message_id;

            RAISE NOTICE '[VerifiedKnowledge] Updated existing entry: message_id=%', NEW.message_id;
        END IF;

    -- 👎 피드백인 경우: 학습에서 제거 처리
    ELSIF NEW.feedback_type = 'thumbs_down' THEN
        UPDATE verified_knowledge
        SET
            thumbs_down_count = thumbs_down_count + 1,
            feedback_score = thumbs_up_count::FLOAT /
                NULLIF(thumbs_up_count + thumbs_down_count + 1, 0),
            -- 👎 받으면 즉시 unlearn_required 상태로 변경
            status = 'unlearn_required',
            unlearn_requested_at = NOW(),
            deprecated_reason = 'User marked as unhelpful (thumbs_down)',
            updated_at = NOW()
        WHERE message_id = NEW.message_id;

        RAISE NOTICE '[VerifiedKnowledge] Marked for unlearning: message_id=%', NEW.message_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 7. Recreate the trigger
CREATE TRIGGER trigger_auto_register_verified_knowledge
    AFTER INSERT ON user_feedbacks
    FOR EACH ROW
    EXECUTE FUNCTION auto_register_verified_knowledge();

-- ============================================
-- Migration complete
-- ============================================
