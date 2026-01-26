"""
Synonym Dictionary for RAG Search Enhancement

도메인 특화 동의어 사전으로 검색 품질 향상
- 기술 용어 변형 (VSAM, vsam, 비샘)
- 다국어 동의어 (OpenFrame, 오픈프레임)
- 약어 확장 (JCL, Job Control Language)
"""

import re
import logging
from typing import List, Set, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SynonymDictionary:
    """
    Domain-specific synonym dictionary for query expansion.

    Improves RAG search by:
    1. Expanding queries with synonyms
    2. Normalizing technical terms
    3. Handling multilingual variations
    """

    def __init__(self):
        # Bidirectional synonym groups
        # Each group contains terms that should match each other
        self._synonym_groups: List[Set[str]] = [
            # =================================================================
            # OpenFrame Products & Components
            # =================================================================
            {"openframe", "오픈프레임", "オープンフレーム", "open frame", "of"},
            {"openframe base", "오픈프레임 베이스", "openframe-base", "of base"},
            {"openframe batch", "오픈프레임 배치", "openframe-batch", "of batch", "ofbatch"},
            {"openframe online", "오픈프레임 온라인", "openframe-online", "of online"},
            {"openframe manager", "오픈프레임 매니저", "ofmanager", "of manager"},
            {"openframe miner", "오픈프레임 마이너", "ofminer", "of miner"},
            {"tmax", "티맥스", "ティーマックス"},
            {"tibero", "티베로", "ティベロ", "tb"},
            {"prosort", "프로소트", "프로 소트"},
            {"jeus", "제우스", "ジェウス"},

            # OpenFrame specific terms
            {"ofsys", "of시스템", "openframe system"},
            {"ofgw", "오픈프레임 게이트웨이", "openframe gateway"},
            {"ofasm", "오픈프레임 어셈블러", "openframe assembler"},
            {"ofcobol", "오픈프레임 코볼", "openframe cobol"},
            {"tacf", "타크프", "tmax access control facility"},
            {"textfld", "텍스트필드", "text field"},
            {"tmadmin", "티엠어드민", "tmax admin"},
            {"tmboot", "티엠부트", "tmax boot"},
            {"tmdown", "티엠다운", "tmax down"},

            # =================================================================
            # VSAM Related (expanded)
            # =================================================================
            {"vsam", "비샘", "비쌤", "v-sam", "virtual storage access method"},
            {"non-vsam", "nonvsam", "non vsam", "비vsam", "논vsam", "non-v-sam", "일반파일"},
            {"ksds", "key sequenced data set", "키순차데이터셋", "key-sequenced"},
            {"esds", "entry sequenced data set", "입력순차데이터셋", "entry-sequenced"},
            {"rrds", "relative record data set", "상대레코드데이터셋", "relative-record"},
            {"lds", "linear data set", "선형데이터셋"},
            {"alternate index", "대체인덱스", "보조인덱스", "aix"},
            {"cluster", "클러스터", "クラスター", "vsam cluster"},
            {"base cluster", "기본클러스터", "베이스클러스터"},

            # =================================================================
            # JCL Related (expanded)
            # =================================================================
            {"jcl", "job control language", "잡컨트롤랭귀지", "작업제어언어"},
            {"jcllib", "jcl library", "jcl 라이브러리"},
            {"proclib", "procedure library", "프로시저 라이브러리", "proc lib"},
            {"ddname", "dd name", "dd네임", "데이터정의명", "dd명"},
            {"dsn", "dataset name", "dsname", "데이터셋명", "데이터셋이름"},
            {"exec", "execute", "실행", "exec문"},
            {"parm", "parameter", "파라미터", "매개변수"},
            {"disp", "disposition", "처분", "디스포지션"},
            {"sysout", "system output", "시스아웃", "시스템출력"},
            {"sysin", "system input", "시스인", "시스템입력"},
            {"sysprint", "시스프린트", "system print"},
            {"sysudump", "시스유덤프", "system dump"},
            {"cond", "condition", "조건", "콘드"},
            {"region", "리전", "리젼", "영역"},

            # =================================================================
            # COBOL Related (expanded)
            # =================================================================
            {"cobol", "코볼", "コボル", "common business oriented language"},
            {"copybook", "카피북", "copy book", "コピーブック", "복사책"},
            {"working-storage", "working storage", "워킹스토리지", "작업저장소"},
            {"procedure division", "프로시저 디비전", "절차부", "절차부문"},
            {"data division", "데이터 디비전", "자료부", "데이터부문"},
            {"identification division", "식별부", "identification"},
            {"environment division", "환경부", "environment"},
            {"pic", "picture", "픽쳐", "그림절"},
            {"comp", "computational", "컴프", "계산형"},
            {"comp-3", "packed decimal", "팩드데시멀", "압축십진"},
            {"perform", "퍼폼", "수행"},
            {"call", "콜", "호출"},

            # =================================================================
            # IMS Related (expanded)
            # =================================================================
            {"ims", "아이엠에스", "information management system"},
            {"ims db", "ims database", "ims 데이터베이스", "ims-db"},
            {"ims tm", "ims transaction manager", "ims 트랜잭션관리자"},
            {"dbd", "database description", "데이터베이스정의", "db정의"},
            {"psb", "program specification block", "프로그램스펙블록"},
            {"pcb", "program communication block", "프로그램통신블록"},
            {"mfs", "message format service", "메시지포맷서비스"},
            {"mid", "message input descriptor", "메시지입력기술자"},
            {"mod", "message output descriptor", "메시지출력기술자"},
            {"dif", "device input format", "디바이스입력포맷"},
            {"dof", "device output format", "디바이스출력포맷"},
            {"bmp", "batch message processing", "배치메시지처리"},
            {"dlibatch", "dli batch", "dli 배치"},

            # =================================================================
            # CICS Related (expanded)
            # =================================================================
            {"cics", "씨익스", "시익스", "customer information control system"},
            {"cics transaction", "cics 트랜잭션", "cics트랜잭션"},
            {"tct", "terminal control table", "터미널제어테이블"},
            {"ppt", "processing program table", "프로그램처리테이블"},
            {"pct", "program control table", "프로그램제어테이블"},
            {"fct", "file control table", "파일제어테이블"},
            {"eibtrnid", "트랜잭션id", "transaction id"},
            {"commarea", "communication area", "통신영역"},

            # =================================================================
            # Database (Tibero/DB2)
            # =================================================================
            {"db2", "디비투", "database 2"},
            {"sql", "에스큐엘", "structured query language"},
            {"dsnzparm", "디에스엔지팜", "db2 system parameters"},
            {"tablespace", "테이블스페이스", "테이블 공간"},
            {"index", "인덱스", "索引"},
            {"cursor", "커서", "カーソル"},
            {"commit", "커밋", "コミット"},
            {"rollback", "롤백", "ロールバック"},

            # =================================================================
            # Batch Processing (expanded)
            # =================================================================
            {"batch", "배치", "バッチ", "일괄처리"},
            {"job", "잡", "ジョブ", "작업"},
            {"step", "스텝", "ステップ", "단계"},
            {"abend", "에이벤드", "abnormal end", "비정상종료"},
            {"restart", "재시작", "リスタート", "재기동"},
            {"checkpoint", "체크포인트", "チェックポイント", "검사점"},
            {"submission", "제출", "サブミット"},

            # =================================================================
            # Utilities (expanded)
            # =================================================================
            {"sort", "소트", "ソート", "정렬"},
            {"merge", "머지", "マージ", "병합"},
            {"idcams", "아이디캠스", "access method services", "ams"},
            {"iebgener", "아이이비제너", "iebgener 유틸리티"},
            {"iebcopy", "아이이비카피", "iebcopy 유틸리티"},
            {"iefbr14", "아이이에프비알14", "dummy job"},
            {"repro", "리프로", "reproduce", "복제"},
            {"define", "디파인", "정의"},
            {"delete", "딜리트", "삭제"},
            {"listcat", "리스트캣", "list catalog"},
            {"print", "프린트", "인쇄"},

            # =================================================================
            # Error/Return Codes (expanded)
            # =================================================================
            {"return code", "리턴코드", "반환코드", "rc"},
            {"condition code", "컨디션코드", "조건코드", "cc"},
            {"abend code", "에이벤드코드", "비정상종료코드"},
            {"s0c4", "에스제로씨포", "storage protection exception"},
            {"s0c7", "에스제로씨세븐", "data exception"},
            {"s0cb", "에스제로씨비", "divide by zero"},
            {"s806", "에스팔공육", "program not found"},
            {"s913", "에스구일삼", "dataset not available"},
            {"s322", "에스삼이이", "time out"},

            # =================================================================
            # System Components (expanded)
            # =================================================================
            {"jes", "jes2", "jes3", "job entry subsystem"},
            {"spool", "스풀", "スプール"},
            {"catalog", "카탈로그", "カタログ"},
            {"vtoc", "volume table of contents", "볼륨목차"},
            {"master catalog", "마스터카탈로그", "기본카탈로그"},
            {"user catalog", "유저카탈로그", "사용자카탈로그"},
            {"volume", "볼륨", "ボリューム"},
            {"dasd", "다스드", "direct access storage device"},

            # =================================================================
            # Common Operations
            # =================================================================
            {"install", "설치", "インストール", "installation"},
            {"configure", "설정", "구성", "configuration", "컨피그"},
            {"error", "에러", "오류", "エラー"},
            {"exception", "예외", "익셉션"},
            {"migration", "마이그레이션", "이전", "이행"},
            {"conversion", "변환", "컨버전"},
            {"rehosting", "리호스팅", "재호스팅"},
            {"compile", "컴파일", "コンパイル"},
            {"link", "링크", "リンク", "연결"},
            {"execute", "실행", "エグゼキュート"},

            # =================================================================
            # File Operations (expanded)
            # =================================================================
            {"dataset", "데이터셋", "데이터세트", "data set", "データセット"},
            {"file", "파일", "ファイル"},
            {"record", "레코드", "レコード"},
            {"member", "멤버", "メンバー"},
            {"pds", "partitioned data set", "분할데이터셋"},
            {"pdse", "partitioned data set extended", "확장분할데이터셋"},
            {"sequential", "순차", "シーケンシャル"},
            {"gds", "generation data set", "세대데이터셋"},
            {"gdg", "generation data group", "세대데이터그룹"},

            # =================================================================
            # Common Terms
            # =================================================================
            {"overview", "개요", "概要", "소개", "introduction"},
            {"guide", "가이드", "ガイド", "안내"},
            {"reference", "레퍼런스", "リファレンス", "참조"},
            {"manual", "매뉴얼", "マニュアル", "설명서"},
            {"tutorial", "튜토리얼", "チュートリアル", "입문"},
            {"example", "예제", "サンプル", "sample", "샘플"},
            {"syntax", "구문", "シンタックス", "문법"},
            {"parameter", "파라미터", "パラメータ", "매개변수"},
        ]

        # Build lookup index: term -> group index
        self._term_to_group: Dict[str, int] = {}
        for group_idx, group in enumerate(self._synonym_groups):
            for term in group:
                self._term_to_group[term.lower()] = group_idx

        logger.info(f"[SynonymDictionary] Loaded {len(self._synonym_groups)} synonym groups, "
                   f"{len(self._term_to_group)} terms indexed")

    def get_synonyms(self, term: str) -> Set[str]:
        """
        Get all synonyms for a given term.

        Args:
            term: The term to look up

        Returns:
            Set of synonyms (including the original term)
        """
        term_lower = term.lower().strip()

        if term_lower in self._term_to_group:
            group_idx = self._term_to_group[term_lower]
            return self._synonym_groups[group_idx].copy()

        return {term}  # Return original if no synonyms found

    def expand_query(self, query: str) -> Tuple[str, List[str]]:
        """
        Expand a query with synonyms.

        Args:
            query: Original search query

        Returns:
            Tuple of (main_keyword, list of expanded terms)
        """
        query_lower = query.lower().strip()

        # Try to find exact match first
        if query_lower in self._term_to_group:
            synonyms = self.get_synonyms(query_lower)
            logger.info(f"[SynonymDictionary] Exact match: '{query}' -> {len(synonyms)} synonyms")
            return query, list(synonyms)

        # Try to find partial matches
        expanded_terms = set()
        matched_terms = []

        for term in self._term_to_group.keys():
            # Check if term is in query or query is in term
            if term in query_lower or query_lower in term:
                synonyms = self.get_synonyms(term)
                expanded_terms.update(synonyms)
                matched_terms.append(term)

        if expanded_terms:
            logger.info(f"[SynonymDictionary] Partial match: '{query}' matched {matched_terms}, "
                       f"expanded to {len(expanded_terms)} terms")
            return query, list(expanded_terms)

        # No synonyms found
        logger.debug(f"[SynonymDictionary] No synonyms for: '{query}'")
        return query, [query]

    def expand_for_sql_like(self, query: str) -> List[str]:
        """
        Expand query for SQL LIKE patterns.

        Returns list of terms suitable for:
        WHERE content LIKE '%term1%' OR content LIKE '%term2%'

        Args:
            query: Original search query

        Returns:
            List of terms for LIKE matching
        """
        _, expanded = self.expand_query(query)

        # Filter out very short terms to avoid too broad matches
        filtered = [t for t in expanded if len(t) >= 2]

        return filtered if filtered else [query]

    def normalize_term(self, term: str) -> str:
        """
        Normalize a term to its canonical form.

        Args:
            term: Term to normalize

        Returns:
            Canonical form of the term
        """
        term_lower = term.lower().strip()

        if term_lower in self._term_to_group:
            group_idx = self._term_to_group[term_lower]
            # Return first term in group as canonical
            return list(self._synonym_groups[group_idx])[0]

        return term

    def add_synonym_group(self, terms: List[str]) -> None:
        """
        Add a new synonym group dynamically.

        Args:
            terms: List of synonymous terms
        """
        if len(terms) < 2:
            return

        new_group = set(t.lower().strip() for t in terms)
        group_idx = len(self._synonym_groups)

        self._synonym_groups.append(new_group)
        for term in new_group:
            self._term_to_group[term] = group_idx

        logger.info(f"[SynonymDictionary] Added new group: {new_group}")


# Singleton instance
_synonym_dictionary: Optional[SynonymDictionary] = None


def get_synonym_dictionary() -> SynonymDictionary:
    """Get singleton SynonymDictionary instance."""
    global _synonym_dictionary
    if _synonym_dictionary is None:
        _synonym_dictionary = SynonymDictionary()
    return _synonym_dictionary
