-- Migration: 027_verified_knowledge.sql
-- Description: Verified Knowledge Store for Smarter RAG System
-- Features: 👍 받은 Q&A 자동 저장, 학습 파이프라인 연동, 우선순위 검색

-- ============================================
-- 1. Verified Knowledge Table (핵심 테이블)
-- ============================================

CREATE TABLE IF NOT EXISTS verified_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 원본 참조
    message_id UUID NOT NULL,
    conversation_id UUID NOT NULL,
    user_id VARCHAR(100) NOT NULL,

    -- Q&A 쌍
    question TEXT NOT NULL,
    question_embedding vector(4096),
    answer TEXT NOT NULL,
    answer_summary TEXT,  -- 300자 이내 요약

    -- 품질 메트릭
    feedback_score FLOAT DEFAULT 1.0,  -- 초기값 1.0 (👍 1개)
    thumbs_up_count INT DEFAULT 1,
    thumbs_down_count INT DEFAULT 0,
    confidence_score FLOAT DEFAULT 0.5,  -- 0-1 스케일
    usage_count INT DEFAULT 0,  -- 재사용 횟수

    -- 분류 메타데이터
    category VARCHAR(100),
    tags TEXT[] DEFAULT '{}',
    language VARCHAR(10) DEFAULT 'ko',
    query_type VARCHAR(50),  -- 'general', 'code', 'api', 'troubleshooting' 등

    -- 원본 소스 정보
    source_documents JSONB DEFAULT '[]',  -- 원본 참조 문서들

    -- 학습 상태
    is_trained BOOLEAN DEFAULT FALSE,
    trained_at TIMESTAMP WITH TIME ZONE,
    training_batch_id VARCHAR(50),
    training_version INT DEFAULT 0,

    -- 상태 관리
    -- active: 활성 (학습 대상)
    -- deprecated: 사용 중지 (낮은 피드백)
    -- superseded: 더 나은 답변으로 대체됨
    -- pending_review: 검토 대기
    -- unlearn_required: 👎로 인해 학습에서 제거 필요
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'deprecated', 'superseded', 'pending_review', 'unlearn_required')),
    superseded_by UUID REFERENCES verified_knowledge(id),
    deprecated_reason TEXT,

    -- Unlearn 관리 (👎 시 학습 제거)
    unlearn_requested_at TIMESTAMP WITH TIME ZONE,
    unlearn_completed_at TIMESTAMP WITH TIME ZONE,
    unlearn_batch_id VARCHAR(50),

    -- 검토 정보
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    review_notes TEXT,

    -- 타임스탬프
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,

    -- 유니크 제약 (같은 메시지에 대해 중복 방지)
    CONSTRAINT uk_verified_knowledge_message UNIQUE (message_id)
);

-- ============================================
-- 2. 인덱스 생성
-- ============================================

-- 벡터 검색 인덱스: pgvector 2000 차원 제한으로 PostgreSQL에서는 비활성화
-- 4096 차원 임베딩 검색은 Neo4j 벡터 인덱스 활용
-- 대신 Full-Text Search 인덱스 강화
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_question_fts
ON verified_knowledge USING gin(to_tsvector('simple', question));

CREATE INDEX IF NOT EXISTS idx_verified_knowledge_answer_fts
ON verified_knowledge USING gin(to_tsvector('simple', answer));

-- 품질 기반 검색
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_score
ON verified_knowledge(feedback_score DESC, usage_count DESC)
WHERE status = 'active';

-- 카테고리 및 언어 필터
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_category
ON verified_knowledge(category, language);

-- 상태 필터
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_status
ON verified_knowledge(status);

-- 학습 상태 필터
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_training
ON verified_knowledge(is_trained, feedback_score DESC)
WHERE status = 'active';

-- 태그 검색 (GIN 인덱스)
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_tags
ON verified_knowledge USING gin(tags);

-- 최근 사용 기준 정렬
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_last_used
ON verified_knowledge(last_used_at DESC NULLS LAST);

-- 생성일 기준 정렬
CREATE INDEX IF NOT EXISTS idx_verified_knowledge_created
ON verified_knowledge(created_at DESC);

-- ============================================
-- 3. Training Batches 테이블
-- ============================================

CREATE TABLE IF NOT EXISTS training_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id VARCHAR(50) UNIQUE NOT NULL,  -- e.g., 'batch_20240125_001'

    -- 배치 정보
    total_samples INT DEFAULT 0,
    trained_samples INT DEFAULT 0,

    -- Unlearn 정보 (👎로 제거된 지식)
    unlearn_samples INT DEFAULT 0,  -- 제거 대상 샘플 수
    unlearned_samples INT DEFAULT 0,  -- 실제 제거된 샘플 수

    -- 품질 기준
    min_feedback_score FLOAT DEFAULT 0.8,
    min_thumbs_up INT DEFAULT 1,

    -- 모델 정보
    base_model VARCHAR(100) DEFAULT 'Qwen2.5-7B-Instruct',
    adapter_name VARCHAR(100),  -- e.g., 'lora_adapter_v001'

    -- 상태
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'collecting', 'training', 'unlearning', 'completed', 'failed')),
    error_message TEXT,

    -- 평가 메트릭
    eval_loss FLOAT,
    eval_accuracy FLOAT,
    eval_perplexity FLOAT,

    -- 타임스탬프
    scheduled_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_batches_status
ON training_batches(status, scheduled_at);

-- ============================================
-- 4. Training Schedule 테이블
-- ============================================

CREATE TABLE IF NOT EXISTS training_schedule (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 스케줄 설정
    cron_expression VARCHAR(50) DEFAULT '0 0 * * *',  -- 매일 00:00
    is_enabled BOOLEAN DEFAULT TRUE,

    -- 마지막 실행 정보
    last_run_at TIMESTAMP WITH TIME ZONE,
    last_batch_id VARCHAR(50) REFERENCES training_batches(batch_id),
    last_status VARCHAR(20),

    -- 다음 실행 정보
    next_run_at TIMESTAMP WITH TIME ZONE,

    -- 설정
    min_samples_required INT DEFAULT 10,  -- 최소 학습 샘플 수
    auto_deploy BOOLEAN DEFAULT FALSE,  -- 자동 배포 여부

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- 5. Knowledge Usage Log (사용 추적)
-- ============================================

CREATE TABLE IF NOT EXISTS knowledge_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    knowledge_id UUID REFERENCES verified_knowledge(id) ON DELETE CASCADE,
    conversation_id UUID,
    user_id VARCHAR(100),

    -- 사용 컨텍스트
    query TEXT NOT NULL,
    similarity_score FLOAT,
    was_helpful BOOLEAN,  -- 후속 피드백

    -- 소스 타입
    source_type VARCHAR(20) DEFAULT 'verified' CHECK (source_type IN ('verified', 'learning_llm', 'hybrid')),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_usage_knowledge_id
ON knowledge_usage_log(knowledge_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_usage_created
ON knowledge_usage_log(created_at DESC);

-- ============================================
-- 6. 자동 등록 트리거 함수
-- ============================================

CREATE OR REPLACE FUNCTION auto_register_verified_knowledge()
RETURNS TRIGGER AS $$
DECLARE
    v_question TEXT;
    v_answer TEXT;
    v_conversation_id UUID;
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
                NEW.conversation_id::UUID,
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

-- 트리거 생성
DROP TRIGGER IF EXISTS trigger_auto_register_verified_knowledge ON user_feedbacks;
CREATE TRIGGER trigger_auto_register_verified_knowledge
    AFTER INSERT ON user_feedbacks
    FOR EACH ROW
    EXECUTE FUNCTION auto_register_verified_knowledge();

-- ============================================
-- 7. Verified Knowledge 통계 뷰
-- ============================================

CREATE OR REPLACE VIEW v_verified_knowledge_stats AS
SELECT
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE status = 'active') as active_count,
    COUNT(*) FILTER (WHERE status = 'deprecated') as deprecated_count,
    COUNT(*) FILTER (WHERE is_trained = TRUE) as trained_count,
    COUNT(*) FILTER (WHERE is_trained = FALSE AND status = 'active') as pending_training_count,
    AVG(feedback_score) FILTER (WHERE status = 'active') as avg_feedback_score,
    AVG(usage_count) FILTER (WHERE status = 'active') as avg_usage_count,
    SUM(usage_count) as total_usage_count,
    COUNT(DISTINCT category) as category_count,
    MAX(created_at) as last_created_at,
    MAX(updated_at) as last_updated_at
FROM verified_knowledge;

-- ============================================
-- 8. 카테고리별 통계 뷰
-- ============================================

CREATE OR REPLACE VIEW v_verified_knowledge_by_category AS
SELECT
    COALESCE(category, 'uncategorized') as category,
    COUNT(*) as count,
    AVG(feedback_score) as avg_score,
    SUM(usage_count) as total_usage,
    COUNT(*) FILTER (WHERE is_trained = TRUE) as trained_count
FROM verified_knowledge
WHERE status = 'active'
GROUP BY category
ORDER BY count DESC;

-- ============================================
-- 9. 학습 준비된 항목 뷰
-- ============================================

CREATE OR REPLACE VIEW v_training_ready_knowledge AS
SELECT
    id,
    question,
    answer,
    answer_summary,
    category,
    tags,
    language,
    query_type,
    source_documents,
    feedback_score,
    thumbs_up_count,
    created_at
FROM verified_knowledge
WHERE status = 'active'
  AND is_trained = FALSE
  AND feedback_score >= 0.8
  AND thumbs_up_count >= 1
ORDER BY feedback_score DESC, thumbs_up_count DESC, created_at ASC;

-- ============================================
-- 9-1. Unlearn 대상 항목 뷰 (👎로 제거 필요)
-- ============================================

CREATE OR REPLACE VIEW v_unlearn_required_knowledge AS
SELECT
    id,
    question,
    answer,
    category,
    language,
    query_type,
    training_batch_id,
    training_version,
    thumbs_down_count,
    unlearn_requested_at,
    created_at
FROM verified_knowledge
WHERE status = 'unlearn_required'
  AND is_trained = TRUE  -- 이미 학습된 것만 unlearn 필요
  AND unlearn_completed_at IS NULL  -- 아직 unlearn 안 된 것
ORDER BY unlearn_requested_at ASC;

-- ============================================
-- 10. 일일 통계 뷰
-- ============================================

CREATE OR REPLACE VIEW v_verified_knowledge_daily_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as new_entries,
    COUNT(*) FILTER (WHERE is_trained = TRUE) as trained_entries,
    AVG(feedback_score) as avg_score
FROM verified_knowledge
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================
-- 11. Updated At 트리거
-- ============================================

CREATE OR REPLACE FUNCTION update_verified_knowledge_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_verified_knowledge_timestamp ON verified_knowledge;
CREATE TRIGGER trigger_update_verified_knowledge_timestamp
    BEFORE UPDATE ON verified_knowledge
    FOR EACH ROW
    EXECUTE FUNCTION update_verified_knowledge_timestamp();

-- ============================================
-- 12. 초기 스케줄 설정 삽입
-- ============================================

INSERT INTO training_schedule (
    cron_expression,
    is_enabled,
    next_run_at,
    min_samples_required,
    auto_deploy
)
VALUES (
    '0 0 * * *',  -- 매일 00:00
    TRUE,
    DATE_TRUNC('day', NOW() + INTERVAL '1 day'),  -- 다음 날 00:00
    10,
    FALSE
)
ON CONFLICT DO NOTHING;

-- ============================================
-- Migration complete
-- ============================================

COMMENT ON TABLE verified_knowledge IS 'Verified Knowledge Store: 👍 받은 Q&A 저장소 for Smarter RAG';
COMMENT ON TABLE training_batches IS 'Learning LLM 학습 배치 관리';
COMMENT ON TABLE training_schedule IS 'Learning LLM 학습 스케줄 설정';
COMMENT ON TABLE knowledge_usage_log IS 'Verified Knowledge 사용 추적';
