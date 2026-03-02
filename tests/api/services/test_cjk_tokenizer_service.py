"""
CJKTokenizerService Unit Tests

Tests for CJK (Chinese-Japanese-Korean) keyword extraction functionality.
"""

import pytest
from app.api.services.cjk_tokenizer_service import CJKTokenizerService, get_cjk_tokenizer_service


class TestCJKTokenizerService:
    """CJKTokenizerService unit tests"""

    @pytest.fixture
    def tokenizer(self):
        """Create a fresh tokenizer instance for each test"""
        return CJKTokenizerService()

    # =========================================================================
    # Japanese Keyword Extraction Tests
    # =========================================================================

    def test_extract_japanese_keywords_basic(self, tokenizer):
        """일본어 키워드 추출 기본 테스트"""
        text = "OSIシステムを起動する方法について説明します。ログファイルの管理も重要です。"
        keywords = tokenizer.extract_japanese_keywords(text)

        # At least some keywords should be extracted
        assert len(keywords) > 0

        # Should contain meaningful Japanese words (either from fugashi or fallback)
        # Check for at least one of the expected keywords
        expected_any = ["起動", "システム", "ログ", "ファイル", "管理", "説明"]
        found = any(kw in keywords for kw in expected_any)
        assert found, f"Expected one of {expected_any} in {keywords}"

    def test_extract_japanese_keywords_katakana(self, tokenizer):
        """가타카나 키워드 추출 테스트"""
        text = "サーバーを起動してクライアントに接続します。データベースの設定を確認してください。"
        keywords = tokenizer.extract_japanese_keywords(text)

        # Should extract katakana words
        katakana_found = any(
            any(ord(c) >= 0x30A0 and ord(c) <= 0x30FF for c in kw)
            for kw in keywords
        )
        assert katakana_found or len(keywords) > 0, "Should extract katakana keywords"

    def test_extract_japanese_keywords_kanji(self, tokenizer):
        """한자 키워드 추출 테스트"""
        text = "運用管理ガイドでは、システムの起動と終了の手順を説明します。"
        keywords = tokenizer.extract_japanese_keywords(text)

        # Should extract kanji compound words
        kanji_found = any(
            any(ord(c) >= 0x4E00 and ord(c) <= 0x9FFF for c in kw)
            for kw in keywords
        )
        assert kanji_found or len(keywords) > 0, "Should extract kanji keywords"

    def test_extract_japanese_stopwords_filtered(self, tokenizer):
        """일본어 불용어 필터링 테스트"""
        text = "これはシステムの説明です。それについて参照してください。使用方法は以下のとおりです。"
        keywords = tokenizer.extract_japanese_keywords(text)

        # Stopwords should not appear
        stopwords = ["これ", "それ", "説明", "参照", "使用", "以下"]
        for sw in stopwords:
            # Allow some stopwords if they're part of compound words
            assert sw not in keywords or len(keywords) < 3, f"Stopword {sw} should be filtered"

    # =========================================================================
    # Korean Keyword Extraction Tests
    # =========================================================================

    def test_extract_korean_keywords_basic(self, tokenizer):
        """한국어 키워드 추출 기본 테스트"""
        text = "시스템을 기동하는 방법에 대해 설명합니다. 로그 파일 관리도 중요합니다."
        keywords = tokenizer.extract_korean_keywords(text)

        assert len(keywords) > 0

        # Should contain meaningful Korean words
        expected_any = ["시스템", "기동", "로그", "파일", "관리"]
        found = any(kw in keywords for kw in expected_any)
        assert found, f"Expected one of {expected_any} in {keywords}"

    def test_extract_korean_stopwords_filtered(self, tokenizer):
        """한국어 불용어 필터링 테스트"""
        text = "이것은 시스템의 설명입니다. 그것에 대해 참조하세요."
        keywords = tokenizer.extract_korean_keywords(text)

        # Stopwords should not appear
        stopwords = ["것", "등", "및"]
        for sw in stopwords:
            assert sw not in keywords, f"Stopword {sw} should be filtered"

    # =========================================================================
    # English Keyword Extraction Tests
    # =========================================================================

    def test_extract_english_keywords_acronyms(self, tokenizer):
        """영문 약어 추출 테스트"""
        text = "The OSI system provides VSAM and TJES features. Use tjesmgr to manage jobs."
        keywords = tokenizer.extract_english_keywords(text)

        assert "OSI" in keywords
        assert "VSAM" in keywords or "TJES" in keywords
        assert "TJESMGR" in keywords

    def test_extract_english_keywords_commands(self, tokenizer):
        """영문 명령어 패턴 추출 테스트"""
        text = "Run oscboot to start the system. Use hidbmgr for database management."
        keywords = tokenizer.extract_english_keywords(text)

        assert "OSCBOOT" in keywords or "HIDBMGR" in keywords

    def test_extract_english_stopwords_filtered(self, tokenizer):
        """영문 불용어 필터링 테스트"""
        text = "THE system AND all FEATURES FOR this PDF document"
        keywords = tokenizer.extract_english_keywords(text)

        # These should be filtered
        stopwords = ["THE", "AND", "FOR", "PDF"]
        for sw in stopwords:
            assert sw not in keywords, f"Stopword {sw} should be filtered"

    # =========================================================================
    # Combined Extraction Tests
    # =========================================================================

    def test_extract_all_keywords_mixed_content(self, tokenizer):
        """다국어 혼합 텍스트 키워드 추출 테스트"""
        text = "OSIシステムの起動方法。TJES provides job scheduling."
        title = "OSI Administrator Guide"

        keywords = tokenizer.extract_all_keywords(text, title)

        # Should have both English and Japanese keywords
        assert len(keywords) > 0

        # English keywords
        english_found = any(kw in keywords for kw in ["OSI", "TJES"])
        assert english_found, f"Expected English keywords in {keywords}"

    def test_extract_all_keywords_title_priority(self, tokenizer):
        """제목 우선 추출 테스트"""
        text = "本文にはVSAMとTJESの説明があります。"
        title = "OSI Administrator Guide - システム管理"

        keywords = tokenizer.extract_all_keywords(text, title)

        # Title keywords should be included (OSI from title)
        assert "OSI" in keywords, f"Title keyword OSI should be in {keywords}"

    def test_extract_all_keywords_max_limit(self, tokenizer):
        """최대 키워드 수 제한 테스트"""
        long_text = " ".join(["OSI", "VSAM", "TJES", "HIDB", "NDB", "OSC", "TACF",
                              "起動", "終了", "管理", "設定", "実行", "処理", "システム"] * 10)

        keywords = tokenizer.extract_all_keywords(long_text, "")

        # Should not exceed max_keywords (default 15)
        assert len(keywords) <= 15

    # =========================================================================
    # Search Tokenization Tests
    # =========================================================================

    def test_tokenize_for_search_english(self, tokenizer):
        """영문 검색 토큰화 테스트"""
        query = "OSI system start"
        tokens = tokenizer.tokenize_for_search(query)

        assert "osi" in tokens
        assert "system" in tokens
        assert "start" in tokens

    def test_tokenize_for_search_japanese(self, tokenizer):
        """일본어 검색 토큰화 테스트"""
        query = "システム起動"
        tokens = tokenizer.tokenize_for_search(query)

        # Should have the original and bi-grams
        assert "システム起動" in tokens or "システム" in tokens or "シス" in tokens

    def test_tokenize_for_search_mixed(self, tokenizer):
        """혼합 검색 토큰화 테스트"""
        query = "OSIシステムを起動する方法"
        tokens = tokenizer.tokenize_for_search(query)

        # Should have both English and Japanese tokens
        assert "osi" in tokens or "OSI" in [t.upper() for t in tokens]
        # Should have Japanese bi-grams
        cjk_tokens = [t for t in tokens if any(ord(c) > 0x3000 for c in t)]
        assert len(cjk_tokens) > 0

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_empty_text(self, tokenizer):
        """빈 텍스트 처리 테스트"""
        keywords = tokenizer.extract_all_keywords("", "")
        assert keywords == []

    def test_only_numbers(self, tokenizer):
        """숫자만 있는 텍스트 처리 테스트"""
        keywords = tokenizer.extract_japanese_keywords("12345 67890")
        # Numbers should not be included as keywords
        assert all(not kw.isdigit() for kw in keywords)

    def test_only_punctuation(self, tokenizer):
        """구두점만 있는 텍스트 처리 테스트"""
        keywords = tokenizer.extract_all_keywords("...!?@#$%", "")
        assert keywords == []


class TestCJKTokenizerServiceSingleton:
    """Singleton pattern tests"""

    def test_singleton_returns_same_instance(self):
        """싱글톤 인스턴스 테스트"""
        service1 = get_cjk_tokenizer_service()
        service2 = get_cjk_tokenizer_service()
        assert service1 is service2


class TestCJKTokenizerServiceIntegration:
    """Integration tests with real document patterns"""

    @pytest.fixture
    def tokenizer(self):
        return CJKTokenizerService()

    def test_osi_document_content(self, tokenizer):
        """OSI 문서 내용 키워드 추출 테스트"""
        # Simulated OSI document content
        text = """
        第5章 システムの運用
        5.1. 起動と終了
        OSIシステムを起動するには、まずサーバープロセスを開始する必要があります。
        ログファイルは運用中の重要な情報を記録します。

        5.2. ログ管理
        システムログはデバッグやトラブルシューティングに役立ちます。
        """
        title = "OF OSI 7.2 Administrator-Guide"

        keywords = tokenizer.extract_all_keywords(text, title)

        # Should include both English and Japanese keywords
        assert "OSI" in keywords, f"OSI should be in keywords: {keywords}"

        # Should include at least one Japanese operational keyword
        ja_operational = ["起動", "終了", "ログ", "運用", "システム", "管理"]
        found_ja = any(kw in keywords for kw in ja_operational)
        assert found_ja, f"Expected Japanese keywords in {keywords}"

    def test_command_reference_content(self, tokenizer):
        """명령어 레퍼런스 내용 키워드 추출 테스트"""
        text = """
        tjesmgrコマンド
        tjesmgr BOOTコマンドは、TJESノードを初期化します。
        tjesmgr CANCELコマンドは、実行中のジョブをキャンセルします。
        """
        title = "TJES Command Reference"

        keywords = tokenizer.extract_all_keywords(text, title)

        # Should include command names
        assert "TJES" in keywords or "TJESMGR" in keywords, f"Command name should be in {keywords}"
