-- ====================================================================
-- Migration: 005_metadata_tables.sql
-- Description: Create metadata configuration tables and seed initial data
-- Created: 2026-01-29
-- ====================================================================

-- Enable UUID extension if not exists
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ====================================================================
-- 1. domain_glossary - 도메인 용어 사전
-- ====================================================================
CREATE TABLE IF NOT EXISTS domain_glossary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term VARCHAR(100) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(50) DEFAULT 'system',
    translations JSONB DEFAULT '{}',
    equivalent_to VARCHAR(255),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_glossary_term ON domain_glossary(term);
CREATE INDEX IF NOT EXISTS idx_glossary_category ON domain_glossary(category);
CREATE INDEX IF NOT EXISTS idx_glossary_active ON domain_glossary(active) WHERE active = TRUE;

-- Initial data: domain_glossary (기존 _CORE_TERMS에서 마이그레이션)
INSERT INTO domain_glossary (term, full_name, description, category, equivalent_to) VALUES
-- System Components
('TJES', 'Tmax Job Entry Subsystem', 'Batch job scheduling and management system', 'system', 'JES2/JES3'),
('TACF', 'Tmax Access Control Facility', 'Security and access control system', 'system', 'RACF'),
('HIDB', 'Hierarchical Database', 'IMS-compatible hierarchical database', 'database', 'IMS DB'),
('OSC', 'Online Service Controller', 'CICS-compatible online transaction processor', 'system', 'CICS'),
('OSI', 'OpenFrame System Interface', 'System interface layer', 'system', NULL),
('NDB', 'Network Database', 'Network database support', 'database', 'IMS DB'),
('AIM', 'Application Integration Manager', 'Application integration framework', 'system', NULL),
('OFMANAGER', 'OpenFrame Manager', 'Central management console', 'system', NULL),
('OFMINER', 'OpenFrame Miner', 'Analytics and mining tool', 'tool', NULL),
('OFSTUDIO', 'OpenFrame Studio', 'Development IDE', 'tool', NULL),
('JEUS', 'JEUS Application Server', 'Java EE application server', 'system', 'WebSphere'),
('WEBTOB', 'WebtoB Web Server', 'High-performance web server', 'system', 'Apache/IHS'),
('TMAX', 'Tmax TP Monitor', 'Transaction processing monitor', 'system', 'CICS'),

-- VSAM Types
('KSDS', 'Key Sequenced Data Set', 'VSAM key-ordered dataset', 'vsam', 'VSAM KSDS'),
('ESDS', 'Entry Sequenced Data Set', 'VSAM entry-ordered dataset', 'vsam', 'VSAM ESDS'),
('RRDS', 'Relative Record Data Set', 'VSAM relative record dataset', 'vsam', 'VSAM RRDS'),
('GDG', 'Generation Data Group', 'Versioned dataset group', 'dataset', 'GDG'),
('PDS', 'Partitioned Data Set', 'Library/member dataset', 'dataset', 'PDS'),

-- Utilities
('ADRDSSU', 'ADRDSSU Utility', 'Dataset dump and restore utility', 'utility', 'ADRDSSU'),
('IDCAMS', 'IDCAMS Utility', 'VSAM catalog services utility', 'utility', 'IDCAMS'),
('IEBCOPY', 'IEBCOPY Utility', 'Dataset copy utility', 'utility', 'IEBCOPY'),
('IEBGENER', 'IEBGENER Utility', 'Sequential dataset copy utility', 'utility', 'IEBGENER'),
('DFSORT', 'DFSORT Utility', 'Sort/merge utility', 'utility', 'DFSORT'),
('DSMIGIN', 'DSMIGIN Utility', 'Dataset migration in utility', 'utility', NULL),
('DSMIGOUT', 'DSMIGOUT Utility', 'Dataset migration out utility', 'utility', NULL)
ON CONFLICT (term) DO NOTHING;

-- ====================================================================
-- 2. document_mappings - 키워드-문서 매핑
-- ====================================================================
CREATE TABLE IF NOT EXISTS document_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword VARCHAR(100) NOT NULL,
    document_pattern VARCHAR(255) NOT NULL,
    category VARCHAR(50) DEFAULT 'product',
    priority INT DEFAULT 100,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(keyword, document_pattern)
);

CREATE INDEX IF NOT EXISTS idx_doc_mapping_keyword ON document_mappings(keyword);
CREATE INDEX IF NOT EXISTS idx_doc_mapping_active ON document_mappings(active) WHERE active = TRUE;

-- Initial data: document_mappings (기존 query_patterns에서 마이그레이션)
INSERT INTO document_mappings (keyword, document_pattern, category, priority) VALUES
-- Product names -> Document patterns
('HIDB', 'HiDB', 'product', 10),
('TJES', 'TJES', 'product', 10),
('TACF', 'TACF', 'product', 10),
('OSC', 'OSC', 'product', 10),
('OSI', 'OSI', 'product', 10),
('NDB', 'NDB', 'product', 10),
('AIM', 'AIM', 'product', 10),
('BASE', 'Base', 'product', 10),
('BATCH', 'Batch', 'product', 10),

-- Utility names -> Utility document
('ADRDSSU', 'Utility', 'utility', 20),
('IDCAMS', 'Utility', 'utility', 20),
('IEBCOPY', 'Utility', 'utility', 20),
('IEBGENER', 'Utility', 'utility', 20),
('DFSORT', 'Utility', 'utility', 20),
('SORT', 'Utility', 'utility', 20),
('DSMIGIN', 'Utility', 'utility', 20),
('DSMIGOUT', 'Utility', 'utility', 20),
('REPRO', 'Utility', 'utility', 20),
('DEFINE', 'Utility', 'utility', 20),
('DELETE', 'Utility', 'utility', 20),
('LISTCAT', 'Utility', 'utility', 20),
('ALTER', 'Utility', 'utility', 20),
('DUMP', 'Utility', 'utility', 20),
('RESTORE', 'Utility', 'utility', 20),

-- Configuration files -> Configuration document
('DS.CONF', 'Configuration', 'config', 30),
('TJES.CONF', 'Configuration', 'config', 30),
('OSC.CONF', 'Configuration', 'config', 30),
('TACF.CONF', 'Configuration', 'config', 30),
('HIDB.CONF', 'Configuration', 'config', 30),
('OFM.CONF', 'Configuration', 'config', 30),

-- Commands -> Specific documents
('TJESMGR', 'TJES', 'command', 15),
('TACFMGR', 'TACF', 'command', 15),
('HIDBMGR', 'HiDB', 'command', 15),
('OSCMGR', 'OSC', 'command', 15),
('OSIMGR', 'OSI', 'command', 15),
('NDBMGR', 'NDB', 'command', 15),
('CATMGR', 'Base', 'command', 15),
('VOLMGR', 'Base', 'command', 15)
ON CONFLICT (keyword, document_pattern) DO NOTHING;

-- ====================================================================
-- 3. error_code_ranges - 에러 코드 범위
-- ====================================================================
CREATE TABLE IF NOT EXISTS error_code_ranges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module VARCHAR(50) NOT NULL,
    range_start INT NOT NULL,
    range_end INT NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    category VARCHAR(50),
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(module, range_start, range_end)
);

CREATE INDEX IF NOT EXISTS idx_error_range_module ON error_code_ranges(module);
CREATE INDEX IF NOT EXISTS idx_error_range_start ON error_code_ranges(range_start);

-- Initial data: error_code_ranges (기존 module_ranges에서 마이그레이션)
INSERT INTO error_code_ranges (module, range_start, range_end, file_path, category) VALUES
-- BASE module
('BASE', 0, 999, 'BASE-0.md', 'system'),
('BASE', 1000, 1999, 'BASE-1000.md', 'dataset'),
('BASE', 2000, 2999, 'BASE-2000.md', 'memory'),
('BASE', 3000, 3999, 'BASE-3000.md', 'io'),
('BASE', 4000, 4999, 'BASE-4000.md', 'process'),
('BASE', 5000, 5999, 'BASE-5000.md', 'allocation'),
('BASE', 6000, 6999, 'BASE-6000.md', 'catalog'),
('BASE', 7000, 7999, 'BASE-7000.md', 'volume'),
('BASE', 8000, 8999, 'BASE-8000.md', 'utility'),

-- BATCH module
('BATCH', 9000, 9999, 'BATCH-9000.md', 'batch'),
('BATCH', 10000, 10999, 'BATCH-10000.md', 'job'),
('BATCH', 11000, 11999, 'BATCH-11000.md', 'step'),
('BATCH', 12000, 12999, 'BATCH-12000.md', 'pgm'),

-- OSC module
('OSC', 13000, 13999, 'OSC-13000.md', 'osc'),
('OSC', 14000, 14999, 'OSC-14000.md', 'transaction'),
('OSC', 15000, 15999, 'OSC-15000.md', 'screen'),

-- OSI module
('OSI', 16000, 16999, 'OSI-16000.md', 'interface'),
('OSI', 17000, 17999, 'OSI-17000.md', 'protocol'),

-- TACF module
('TACF', 18000, 18999, 'TACF-18000.md', 'security'),
('TACF', 19000, 19999, 'TACF-19000.md', 'auth'),

-- HIDB module
('HIDB', 20000, 20999, 'HIDB-20000.md', 'database'),

-- AIM module
('AIM', 21000, 21999, 'AIM-21000.md', 'integration'),

-- NDB module
('NDB', 22000, 22999, 'NDB-22000.md', 'network'),

-- TJES module
('TJES', 23000, 23999, 'TJES-23000.md', 'jes'),
('TJES', 24000, 24999, 'TJES-24000.md', 'spool'),
('TJES', 25000, 25999, 'TJES-25000.md', 'queue'),

-- OFMANAGER module
('OFMANAGER', 26000, 26999, 'OFMANAGER-26000.md', 'manager'),
('OFMINER', 27000, 27999, 'OFMINER-27000.md', 'miner'),
('OFSTUDIO', 28000, 28999, 'OFSTUDIO-28000.md', 'studio'),

-- System modules
('SYSTEM', 29000, 29999, 'SYSTEM-29000.md', 'system'),
('NETWORK', 30000, 30999, 'NETWORK-30000.md', 'network'),

-- Legacy modules (negative ranges stored as positive)
('VSAM', 100, 999, 'VSAM-100.md', 'vsam'),
('JCL', 1000, 1999, 'JCL-1000.md', 'jcl'),
('COBOL', 2000, 2999, 'COBOL-2000.md', 'cobol'),
('ASM', 3000, 3999, 'ASM-3000.md', 'assembler')
ON CONFLICT (module, range_start, range_end) DO NOTHING;

-- ====================================================================
-- 4. synonyms - 동의어
-- ====================================================================
CREATE TABLE IF NOT EXISTS synonyms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    base_term VARCHAR(255) NOT NULL,
    synonym VARCHAR(255) NOT NULL,
    language VARCHAR(10) NOT NULL,
    domain VARCHAR(50) DEFAULT 'general',
    confidence FLOAT DEFAULT 1.0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(base_term, synonym, language)
);

CREATE INDEX IF NOT EXISTS idx_synonyms_base_term ON synonyms(base_term);
CREATE INDEX IF NOT EXISTS idx_synonyms_language ON synonyms(language);

-- Initial data: synonyms (기존 query_expansion_service에서 마이그레이션)
INSERT INTO synonyms (base_term, synonym, language, domain, confidence) VALUES
-- Japanese synonyms
('DATASET', 'データセット', 'ja', 'technical', 1.0),
('FILE', 'ファイル', 'ja', 'technical', 1.0),
('JOB', 'ジョブ', 'ja', 'technical', 1.0),
('BATCH', 'バッチ', 'ja', 'technical', 1.0),
('ERROR', 'エラー', 'ja', 'technical', 1.0),
('COMMAND', 'コマンド', 'ja', 'technical', 1.0),
('CONFIG', '設定', 'ja', 'technical', 1.0),
('PARAMETER', 'パラメータ', 'ja', 'technical', 1.0),
('PROCESS', 'プロセス', 'ja', 'technical', 1.0),
('TRANSACTION', 'トランザクション', 'ja', 'technical', 1.0),
('DATABASE', 'データベース', 'ja', 'technical', 1.0),
('CATALOG', 'カタログ', 'ja', 'technical', 1.0),
('VOLUME', 'ボリューム', 'ja', 'technical', 1.0),
('DUMP', 'ダンプ', 'ja', 'technical', 1.0),
('RESTORE', 'リストア', 'ja', 'technical', 1.0),
('BACKUP', 'バックアップ', 'ja', 'technical', 1.0),
('COPY', 'コピー', 'ja', 'technical', 1.0),
('SORT', 'ソート', 'ja', 'technical', 1.0),
('MIGRATION', 'マイグレーション', 'ja', 'technical', 1.0),

-- Korean synonyms
('DATASET', '데이터셋', 'ko', 'technical', 1.0),
('FILE', '파일', 'ko', 'technical', 1.0),
('JOB', '작업', 'ko', 'technical', 1.0),
('BATCH', '배치', 'ko', 'technical', 1.0),
('ERROR', '에러', 'ko', 'technical', 1.0),
('ERROR', '오류', 'ko', 'technical', 0.9),
('COMMAND', '명령어', 'ko', 'technical', 1.0),
('COMMAND', '커맨드', 'ko', 'technical', 0.9),
('CONFIG', '설정', 'ko', 'technical', 1.0),
('CONFIG', '구성', 'ko', 'technical', 0.9),
('PARAMETER', '파라미터', 'ko', 'technical', 1.0),
('PARAMETER', '매개변수', 'ko', 'technical', 0.9),
('PROCESS', '프로세스', 'ko', 'technical', 1.0),
('TRANSACTION', '트랜잭션', 'ko', 'technical', 1.0),
('DATABASE', '데이터베이스', 'ko', 'technical', 1.0),
('CATALOG', '카탈로그', 'ko', 'technical', 1.0),
('VOLUME', '볼륨', 'ko', 'technical', 1.0),
('DUMP', '덤프', 'ko', 'technical', 1.0),
('RESTORE', '복원', 'ko', 'technical', 1.0),
('BACKUP', '백업', 'ko', 'technical', 1.0),
('COPY', '복사', 'ko', 'technical', 1.0),
('SORT', '정렬', 'ko', 'technical', 1.0),
('MIGRATION', '마이그레이션', 'ko', 'technical', 1.0),
('MIGRATION', '이관', 'ko', 'technical', 0.9),

-- English synonyms/aliases
('DATASET', 'data set', 'en', 'technical', 1.0),
('DATASET', 'DSN', 'en', 'technical', 0.9),
('CONFIG', 'configuration', 'en', 'technical', 1.0),
('CONFIG', 'conf', 'en', 'technical', 0.9),
('ERROR', 'failure', 'en', 'technical', 0.8),
('ERROR', 'exception', 'en', 'technical', 0.8)
ON CONFLICT (base_term, synonym, language) DO NOTHING;

-- ====================================================================
-- 5. visual_keywords - 시각 키워드
-- ====================================================================
CREATE TABLE IF NOT EXISTS visual_keywords (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL,
    category VARCHAR(50) DEFAULT 'diagram',
    weight FLOAT DEFAULT 1.0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(keyword, language)
);

CREATE INDEX IF NOT EXISTS idx_visual_kw_language ON visual_keywords(language);
CREATE INDEX IF NOT EXISTS idx_visual_kw_category ON visual_keywords(category);

-- Initial data: visual_keywords (기존 opencode_service에서 마이그레이션)
INSERT INTO visual_keywords (keyword, language, category, weight) VALUES
-- Japanese
('図', 'ja', 'diagram', 1.0),
('プロセス図', 'ja', 'diagram', 1.2),
('フローチャート', 'ja', 'diagram', 1.2),
('フロー図', 'ja', 'diagram', 1.2),
('構成図', 'ja', 'diagram', 1.1),
('アーキテクチャ図', 'ja', 'diagram', 1.1),
('シーケンス図', 'ja', 'diagram', 1.1),
('テーブル', 'ja', 'table', 1.0),
('表', 'ja', 'table', 1.0),
('一覧', 'ja', 'table', 0.9),
('フォーマット', 'ja', 'format', 0.8),
('形式', 'ja', 'format', 0.8),
('構造', 'ja', 'format', 0.8),
('チャート', 'ja', 'chart', 1.0),
('グラフ', 'ja', 'chart', 1.0),
('画像', 'ja', 'image', 1.0),
('スクリーンショット', 'ja', 'image', 0.9),

-- Korean
('그림', 'ko', 'diagram', 1.0),
('프로세스도', 'ko', 'diagram', 1.2),
('플로우차트', 'ko', 'diagram', 1.2),
('흐름도', 'ko', 'diagram', 1.2),
('구성도', 'ko', 'diagram', 1.1),
('아키텍처도', 'ko', 'diagram', 1.1),
('시퀀스도', 'ko', 'diagram', 1.1),
('테이블', 'ko', 'table', 1.0),
('표', 'ko', 'table', 1.0),
('목록', 'ko', 'table', 0.9),
('포맷', 'ko', 'format', 0.8),
('형식', 'ko', 'format', 0.8),
('구조', 'ko', 'format', 0.8),
('차트', 'ko', 'chart', 1.0),
('그래프', 'ko', 'chart', 1.0),
('이미지', 'ko', 'image', 1.0),
('스크린샷', 'ko', 'image', 0.9),

-- English
('diagram', 'en', 'diagram', 1.0),
('flowchart', 'en', 'diagram', 1.2),
('flow diagram', 'en', 'diagram', 1.2),
('process diagram', 'en', 'diagram', 1.2),
('architecture diagram', 'en', 'diagram', 1.1),
('sequence diagram', 'en', 'diagram', 1.1),
('table', 'en', 'table', 1.0),
('list', 'en', 'table', 0.9),
('format', 'en', 'format', 0.8),
('structure', 'en', 'format', 0.8),
('chart', 'en', 'chart', 1.0),
('graph', 'en', 'chart', 1.0),
('image', 'en', 'image', 1.0),
('screenshot', 'en', 'image', 0.9),
('picture', 'en', 'image', 0.9)
ON CONFLICT (keyword, language) DO NOTHING;

-- ====================================================================
-- Summary
-- ====================================================================
-- Tables created: 5
-- - domain_glossary: 26 initial terms
-- - document_mappings: 39 initial mappings
-- - error_code_ranges: 35 initial ranges
-- - synonyms: 50 initial synonyms
-- - visual_keywords: 51 initial keywords
--
-- Total initial data: 201 records
-- ====================================================================
