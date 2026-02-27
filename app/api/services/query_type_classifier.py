"""
Query Type Classifier

Regex 기반 질문 유형 분류기.
COMMAND, ERROR_CODE, PARAMETER, CONFIG, FREEFORM을 판별합니다.
"""
import re
import logging
from typing import Optional

from ..models.agentic_rag import QueryType

logger = logging.getLogger(__name__)


class QueryTypeClassifier:
    """
    Regex 기반 질문 유형 분류기 (LLM 없음)

    분류 우선순위:
    1. ERROR_CODE: 에러코드 패턴 (-5212, ABEND S0C7 등)
    2. COMMAND: 명령어 패턴 (tjesmgr BOOT, oscmgr 등)
    3. PARAMETER: 파라미터/설정 패턴 (LRECL, RECFM 등)
    4. CONFIG: 설정 파일 패턴 (.conf, 設定 등)
    5. FREEFORM: 위 패턴에 해당하지 않는 일반 질문
    """

    # 에러코드 패턴
    ERROR_CODE_PATTERNS = [
        r'-\d{4,5}',              # -5212, -12345
        r'ABEND\s+S\d{3}',       # ABEND S0C7
        r'에러\s*코드',           # 에러 코드 (Korean)
        r'エラーコード',           # エラーコード (Japanese)
        r'error\s*code',          # error code (English)
        r'エラー.*-?\d{4,5}',     # エラー + 번호
        r'에러.*(?:발생|대처|원인|해결|처리)',  # 에러 + 동작 키워드 (Korean)
        r'(?:발생|대처|원인|해결|처리).*에러',  # 동작 키워드 + 에러 (Korean)
        r'오류.*(?:발생|대처|원인|해결|처리)',  # 오류 + 동작 키워드 (Korean)
        r'エラー.*(?:発生|対処|原因|解決)',     # エラー + 동작 키워드 (Japanese)
        r'(?:発生|対処|原因|解決).*エラー',     # 동작 키워드 + エラー (Japanese)
        r'error.*(?:occur|handling|cause|resolution|troubleshoot)',  # English
    ]

    # 명령어 패턴
    COMMAND_PATTERNS = [
        r'tjesmgr\s+\w+',         # tjesmgr BOOT
        r'tacfmgr\s+\w+',         # tacfmgr LIST
        r'oscmgr\s+\w+',          # oscmgr START
        r'osimgr\s+\w+',          # osimgr
        r'hidbmgr\s+\w+',         # hidbmgr START
        r'catmgr\s+\w+',          # catmgr
        r'volmgr\s+\w+',          # volmgr
        r'ndbmgr\s+\w+',          # ndbmgr
        r'idcams\b',              # IDCAMS
        r'iebgener\b',            # IEBGENER
        r'iebcopy\b',             # IEBCOPY
        r'dfsort\b',              # DFSORT
        r'dsmigin\b',             # DSMIGIN
        r'dsmigout\b',            # DSMIGOUT
        r'OFATOE\b',              # OFATOE (ASCII→EBCDIC)
        r'OFETOA\b',              # OFETOA (EBCDIC→ASCII)
        r'DFSRRC00\b',            # DFSRRC00 (IMS utility)
        r'tmboot\b',              # tmboot
        r'tmdown\b',              # tmdown
        r'ofboot\b',              # ofboot
        r'ofdown\b',              # ofdown
        r'コマンド',               # コマンド (Japanese)
        r'명령어',                 # 명령어 (Korean)
        r'command\s+usage',       # command usage
        r'使い方',                 # 使い方 (how to use)
        r'사용법',                 # 사용법 (Korean: usage)
    ]

    # 파라미터 패턴
    PARAMETER_PATTERNS = [
        r'\bLRECL\b',
        r'\bRECFM\b',
        r'\bBLKSIZE\b',
        r'\bDSORG\b',
        r'\bKEYLEN\b',
        r'パラメータ',             # パラメータ (Japanese)
        r'파라미터',               # 파라미터 (Korean)
        r'parameter\b',
    ]

    # 설정 패턴
    CONFIG_PATTERNS = [
        r'\.conf\b',              # .conf file
        r'設定ファイル',           # 設定ファイル (Japanese)
        r'설정\s*파일',           # 설정 파일 (Korean)
        r'config\s*file',         # config file
        r'configuration\b',
        r'環境設定',               # 環境設定 (Japanese)
        r'환경\s*설정',           # 환경 설정 (Korean)
        r'tjes\.conf',
        r'osc\.conf',
        r'tacf\.conf',
        r'ds\.conf',
        r'oframe\.conf',
    ]

    def classify(self, query: str) -> QueryType:
        """
        쿼리 유형 분류

        Args:
            query: 사용자 쿼리

        Returns:
            QueryType enum value
        """
        query_check = query.lower() if query else ""

        # 우선순위 순서로 검사
        if self._matches(query_check, self.ERROR_CODE_PATTERNS):
            return QueryType.ERROR_CODE

        if self._matches(query_check, self.COMMAND_PATTERNS):
            return QueryType.COMMAND

        if self._matches(query_check, self.PARAMETER_PATTERNS):
            return QueryType.PARAMETER

        if self._matches(query_check, self.CONFIG_PATTERNS):
            return QueryType.CONFIG

        return QueryType.FREEFORM

    def _matches(self, query: str, patterns: list) -> bool:
        """주어진 패턴 리스트 중 하나라도 매칭되는지 확인"""
        for pattern in patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        return False


# Singleton
_classifier_instance: Optional[QueryTypeClassifier] = None


def get_query_type_classifier() -> QueryTypeClassifier:
    """Get singleton QueryTypeClassifier"""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = QueryTypeClassifier()
    return _classifier_instance
