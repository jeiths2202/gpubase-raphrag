"""
Product Router Service

쿼리를 적절한 제품으로 라우팅하는 서비스.
키워드 기반 분류 및 confidence 점수 계산을 수행합니다.
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from ..models.openframe_rag import (
    ProductId,
    ClassificationResult,
    ProductKeywords,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Product Keyword Definitions
# =============================================================================

@dataclass
class ProductConfig:
    """Product configuration with keywords and patterns"""
    product: ProductId
    keywords: List[str]
    patterns: List[str]  # Regex patterns
    weight: float = 1.0


# 제품별 키워드 정의
PRODUCT_CONFIGS: List[ProductConfig] = [
    ProductConfig(
        product=ProductId.OPENFRAME_MVS,
        keywords=[
            # TJES 관련
            "tjes", "tjesmgr", "tjclrun", "jeslog", "tjesmgr", "job entry",
            # JCL 관련
            "jcl", "jclrun", "jesrun", "job", "dd", "exec", "proc", "steplib",
            # MVS 유틸리티
            "idcams", "iebgener", "iebcopy", "iebupdte", "iehprogm",
            "dfsort", "syncsort", "icetool",
            # TACF 관련
            "tacf", "tacfmgr", "racf", "security",
            # 시스템 관리
            "tmboot", "tmdown", "ofboot", "ofdown", "jesinit", "jesdown",
            # OSC 관련 — 管理ツール
            "osc", "oscmgr", "cics", "online",
            "mscasmc", "mscmapc", "mscmapupdate",
            "osccobprep", "osccblpp", "oscplipp", "osccprep", "oschttp",
            "cobolprep", "oscdct2rd", "oscjct2rd",
            # OSC — TDL/システムユーティリティ
            "osctdlrm", "osctdlinit", "osctdlupdate",
            "oscboot", "oscdown", "oscmcsvr", "oscscview", "oscsddump",
            "oscsiggen", "oscdfsvr",
            # OSC — CTG (CICS Transaction Gateway)
            "ctg", "ofctg", "openframe ctg",
            "eciinteractionspec", "cicsinteractionspec", "oivpecit",
            "ccilocaltransaction", "cicsconnection", "eciconnection",
            # OSC — EXEC CICS / BMS / マッピング
            "exec cics", "commarea", "eib", "cvda",
            "dfhmdf", "dfhmdi", "dfhmsd", "dfhcommarea", "dfhcspg",
            "dfhdct", "dfhplt", "dfhxlt", "dfhjct", "dfhwba", "dfhwbun",
            "dfhresp", "dfhpgaco", "dfhsiplt", "dfhdelim",
            "dfhfile", "dfhgrp", "dfhhtml", "dfhlist", "dfhtdq", "dfhtsq",
            "bms", "cspg",
            # OSC — リソース定義 / キュー / 通信
            "tsq", "tdq", "tranclass", "typeterm", "urimap",
            "tcpipservice", "doctemplate", "journalmodel", "tsmodel",
            "grplist", "rtsd",
            # OSC — 端末・通信
            "vtam", "tn3270", "3270", "dpl", "isc", "mro",
            # OSC — 設定ファイル / サーバー
            "ofosc.seq", "osc.region.list", "openframe_osc.conf",
            "oivp", "oivpmain", "osc region", "tcache",
            # OSC — EIB フィールド
            "eibresp", "eibrcode", "eibaid", "eibcalen", "eibtrnid",
            # OSI 관련
            "osi", "osimgr",
            # HiDB 관련 (階層型データベース)
            "hidb", "hidbmgr", "ims", "dl/i", "dli",
            "階層データベース", "階層型データベース", "階層db",
            "dbpcb", "psbgen", "dbd", "psb", "pcb",
            # NDB 관련
            "ndb", "ndbmgr",
            # 기타 MVS
            "mvs", "mainframe", "batch", "spufi", "ispf",
            # IPF / MFS (MVS PDF에서 추출)
            "ipf", "mfs",
        ],
        patterns=[
            r"tjesmgr\s+\w+",      # tjesmgr 명령어
            r"tacfmgr\s+\w+",      # tacfmgr 명령어
            r"oscmgr\s+\w+",       # oscmgr 명령어
            r"osc[a-z]{4,}",       # osc接頭辞ツール (osctdlrm, oscboot 等)
            r"osimgr\s+\w+",       # osimgr 명령어
            r"hidbmgr\s+\w+",      # hidbmgr 명령어
            r"ndbmgr\s+\w+",       # ndbmgr 명령어
            r"\/\/\w+\s+JOB",      # JCL JOB statement
            r"EXEC\s+PGM=",        # JCL EXEC statement
            r"DD\s+DSN=",          # JCL DD statement
            r"-\d{4,5}",           # 에러 코드 패턴
            r"ABEND\s+S\d{3}",     # ABEND 코드
            r"EXEC\s+CICS\s+\w+",  # EXEC CICS 명령어
            r"EXEC\s+DLI\s+\w+",   # EXEC DLI 명령어
            r"(?:OF)?CTG",         # CTG / OFCTG
            r"DFH[A-Z]{3,}",      # DFH 매크로 (DFHMDF, DFHPLT 등)
            r"EIB[A-Z]{2,}",      # EIB 필드 (EIBRESP, EIBAID 등)
        ],
        weight=1.2  # MVS는 가장 일반적이므로 약간 높은 가중치
    ),
    ProductConfig(
        product=ProductId.MSP_OPENFRAME,
        keywords=[
            "msp", "msp openframe", "msp-openframe",
            # JES/SMS/HSM
            "jes2", "jes3", "sms", "hsm", "dfhsm",
            # AIM (Application Integrity Manager)
            "aim", "aimmgr", "aimconv", "aimcheck", "aimutil",
            # NDB (Network Database) - MSP/Fujitsu 계열
            "ndb", "ndbmgr", "ndbgensch", "ndbexport", "ndbimport",
            "ネットワークデータベース", "ネットワークdb",
            # MSP 고유
            "tso", "ispf", "sdsf", "ipcs", "dfsms", "dfp", "ipf",
        ],
        patterns=[
            r"msp\s+\w+",
            r"aimmgr\s+\w+",     # AIM 명령어
            r"ndbmgr\s+\w+",     # NDB 명령어
            r"AIM[-_]\d+",       # AIM 에러 코드
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.VOS3_OPENFRAME,
        keywords=[
            "vos3", "vos3 openframe", "vos3-openframe",
            "acos", "nec", "日立",
            # VOS3 유틸리티
            "adrdump0", "adrinit2", "adrinit3", "adrrest0", "adrdssu",
            "dscopy", "dsutil", "catutil", "volutil",
            # VOS3 설정
            "vos3.conf", "openframe_vos3.conf", "vos3.seq",
            # VOS3도 자체 JCL/TJES 가이드 보유
            "vos3 jcl", "vos3 tjes", "vos3 batch",
        ],
        patterns=[
            r"vos3\s+\w+",
            r"adr\w{4,}",        # ADR 유틸리티
            r"VOS3[-_]\d+",      # VOS3 에러 코드
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OPENFRAME_BASE,
        keywords=[
            # Base 시스템 키워드
            "base", "openframe base", "openframe/base", "of_base",
            # 데이터셋 관련
            "dataset", "dsalc", "dsorg", "recfm", "lrecl", "blksize",
            "vsam", "ksds", "esds", "rrds", "lds",
            # 카탈로그 관련
            "catalog", "catmgr", "alias", "gdg", "generation",
            # 볼륨 관련
            "volume", "volser", "vtoc", "dscb",
            # 파일 시스템
            "pds", "pdse", "sequential", "partitioned",
            # 유틸리티
            "dsmigin", "dsmigout", "listcat", "define",
        ],
        patterns=[
            r"base\s+system",
            r"openframe\s*/?\s*base",
            r"dsalc_\w+",          # DSALC 에러 코드
            r"VSAM\s+\w+",
            r"GDG\s+\w+",
        ],
        weight=1.1  # Base는 일반적인 질문이므로 약간 높은 가중치
    ),
    ProductConfig(
        product=ProductId.TIBERO7,
        keywords=[
            "tibero", "tibero7", "tibero 7", "tbsql", "tbcli",
            "tbdsn", "tbexport", "tbimport", "tbloader",
            "tsql", "tac", "taf", "tbadmin",
            # Tibero 도구
            "tbboot", "tbdown", "tbcm", "tbrmgr", "tbprobe",
            "tbrecover", "tbcrypt", "tbpwd", "tbpc",
            "tbmigrator", "tbgateway", "tbwallet", "tbwrap",
            "tbesql", "tbedit", "tblistener", "tbutil",
            # Tibero 설정
            "tibero.tip", "tbdsn.tbr", "tbnet_alias.tbr",
            "tb_cm.cfg", "tbha.cfg",
            # Tibero 고유 기능
            "tbha", "tbcm", "tsr",
            "active standby", "tibero cluster", "zero downtime",
            # SQL 관련
            "sql", "oracle", "database", "db",
            "select", "insert", "update", "delete",
            "pl/sql", "procedure", "function", "trigger",
            "tablespace", "datafile", "rownum",
            # DBMS 패키지/기능
            "dbms_lock", "dbms_output", "dbms_sql", "dbms_job",
            "dbms_scheduler", "dbms_metadata", "dbms_stats",
            "dbms_lob", "dbms_pipe", "dbms_alert", "dbms_crypto",
            "dbms_random", "dbms_session", "dbms_space",
            "dbms_redefinition", "dbms_xplan", "dbms_repair",
            "dbms_flashback", "dbms_aq", "dbms_aqadm",
            "dbms_resource_manager", "dbms_result_cache",
            "dbms_utility", "dbms_ddl", "dbms_fga",
            "dbms_xmldom", "dbms_xmlgen", "dbms_xmlparser",
            "dbms_rls", "dbms_rowid", "dbms_monitor",
            "dbms_", "package", "パッケージ",
            # tbPSM 관련
            "tbpsm", "psm", "stored procedure",
            # Tibero PDF에서 추출
            "hadoop", "imcs", "spatial", "tdpnet", "tdp.net",
        ],
        patterns=[
            r"tibero\s*\d*",
            r"tb\w+",              # tb로 시작하는 명령어
            r"SELECT\s+.+\s+FROM", # SQL SELECT
            r"dbms_\w+",           # DBMS_* パッケージ
            r"TBR[-_]\d+",        # Tibero 에러 코드
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFASM,
        keywords=[
            "ofasm", "assembler", "asm", "macro",
            "hlasm", "assembler language",
            # ASM 기본 명령어
            "csect", "dsect", "using", "balr", "basr",
            "bcr", "mvc", "mvi", "cli", "clc",
            "pack", "unpk", "cvb", "cvd", "zap",
            "stm", "lm", "sll", "srl",
            # OFASM 도구
            "ofasmif", "ofasma", "ofasmpp", "asmrun",
            # OFASM 기계어 명령
            "ofatoe", "ofetoa",
            # ASM I/O 매크로
            "dcb", "bsam", "qsam",
            # 설정
            "ofasm.conf",
        ],
        patterns=[
            r"ofasm\s+\w+",
            r"CSECT|DSECT|USING|BALR",
            r"ofasm\w*",          # ofasm 접두사 도구
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFCOBOL,
        keywords=[
            "ofcobol", "cobol", "cobc", "cobrun",
            "copybook", "working-storage", "procedure division",
            "file section", "data division",
            "perform", "move", "compute",
            # OFCOBOL 도구
            "ofcob", "ofcbpp", "ofcbppf", "ofcobcpy", "cobmake",
            # COBOL 구문
            "identification division", "environment division",
            "linkage section", "evaluate",
            "string", "unstring", "inspect",
            "exec sql", "goback", "stop run",
            # 컴파일러 옵션
            "dynam", "nodynam", "trunc", "notrunc", "arith",
            "apost", "dbcs",
            # 설정
            "ofcobol.conf", "ofcob.conf",
        ],
        patterns=[
            r"ofcobol\s+\w+",
            r"ofcob\w+",
            r"WORKING-STORAGE\s+SECTION",
            r"PROCEDURE\s+DIVISION",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFPLI,
        keywords=[
            "ofpli", "pli", "pl/i", "pl/1",
            "plirun", "plicomp",
            # PL/I 구문
            "declare", "dcl", "procedure",
            # 설정
            "ofpli.conf",
        ],
        patterns=[
            r"ofpli\s+\w+",
            r"PL/I",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.XSP_OPENFRAME,
        keywords=[
            "xsp", "xsp openframe", "xsp-openframe",
            "xspmgr", "xsp region",
            "xsp.conf", "openframe_xsp.conf",
            # ATMI/Tuxedo 호환
            "atmi",
        ],
        patterns=[
            r"xsp\s+\w+",
            r"xspmgr\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.TMAX,
        keywords=[
            "tmax", "tuxedo", "tmaxsoft",
            # Tmax 핵심 도구
            "tmadmin", "tmaxreadenv",
            "cfl", "gst", "racd",
            # Tmax 프로세스
            "clh", "tlh", "slh", "tmm",
            # Tmax API 함수
            "tpacall", "tpcall", "tpreturn", "tpforward",
            "tpalloc", "tpconnect", "tpdiscon",
            "tpsend", "tprecv", "tpstart", "tpend",
            "tpbegin", "tpcommit", "tpabort", "tprollback",
            "tpscmt", "tpgetlev", "tpbroadcast",
            "tpenqueue", "tpdequeue", "tppost", "tpsubscribe",
            "tpnotify", "tpexport", "tpimport",
            "tpgetctx", "tpsetctx", "tpgetunsol", "tpsetunsol",
            "tuxgetenv", "tuxputenv", "tuxreadenv", "userlog",
            # FDL/SDL/TDL
            "fdl", "sdl", "tdl",
            "svrgroup", "svc", "gwtdomain",
            # FDL 설정 키워드
            "shmkey", "tportno", "maxspr", "maxcpc",
            "minclh", "maxclh", "cportno",
            "tmaxdir", "appdir", "svgname",
            "clopt", "svrtype", "svctimeout", "blocktime",
            # 설정
            "tmax.env", "oframe.m", "tmconfig",
            # 연계
            "wsgw", "jeus connector",
            # Tmax PDF에서 추출
            "hms", "hostlink", "jtc", "jtmaxserver",
            "tmaxgrid", "webtasync", "webtjca",
            "rpc", "rq", "sq", "ucs", "tcache",
        ],
        patterns=[
            r"tmax\s+\w+",
            r"tp\w+",             # tp로 시작하는 함수
            r"tmadmin\s+\w+",     # tmadmin 서브명령어
            r"tms_\w+",           # TMS 프로세스
        ],
        weight=1.0
    ),
    # ===========================================================================
    # 신규 제품 (JEUS, WebtoB, OFGW, OFManager, OFMiner, OFStudio, ProSort, ProSync, ProTrieve)
    # ===========================================================================
    ProductConfig(
        product=ProductId.JEUS,
        keywords=[
            "jeus", "jeus8", "jeus 8",
            # JEUS 핵심 도구
            "jeusadmin", "jspc", "appcompiler", "jeusdeploy",
            "startdomainadminserver", "startmanagedserver",
            "startnodemanager", "stopserver",
            # JEUS 구성요소
            "das", "domainadminserver", "managedserver",
            "nodemanager", "webengine", "ejbengine",
            "jmsengine", "sessionserver",
            "datasource", "connectionpool", "threadpool",
            # JEUS 설정
            "domain.xml", "jeus-web-dd.xml", "jeus-ejb-dd.xml",
            "jeus.properties", "jeus-application-dd.xml",
            # JEUS 프로토콜/기능
            "webadmin", "jndi", "jdbc", "jms",
            "ejb", "jpa", "jta", "jca", "jmx",
            "jaas", "jacc", "jaxb", "jaxrs", "jax-rs",
            "jaxws", "jax-ws", "saaj", "wsit",
            "servlet", "jsp", "jsf", "jstl",
            # JEUS PDF에서 추출
            "jbatch", "mq", "snmp", "scheduler",
        ],
        patterns=[
            r"jeus\s*\d*",
            r"jeusadmin\s+\w+",   # jeusadmin 서브명령어
            r"jeus[-_]\w+\.xml",  # JEUS 설정 파일
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.WEBTOB,
        keywords=[
            "webtob", "webtob5",
            # WebtoB 핵심 도구
            "wsadmin", "wscfl", "wsboot", "wsdown", "wsconfig",
            # WebtoB 서버 프로세스
            "hth", "htl", "htmls",
            "cgis", "ssis", "phps", "jsvs",
            # WebtoB 기능
            "reverseproxy", "vhost", "docroot",
            "errordocument", "filters",
            # WebtoB 설정
            "http.m", "webtob.conf", "node.conf",
            "uri.conf", "vhost.conf", "ssl.conf",
            # WebtoB 프로세스
            "tcpgw", "proxy", "httpd",
        ],
        patterns=[
            r"webtob\s*\d*",
            r"wsadmin\s+\w+",     # wsadmin 서브명령어
            r"http\.m",           # WebtoB 설정 파일
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFGW,
        keywords=[
            "ofgw", "ofgateway", "openframe gateway",
            # OFGW 도구
            "gwcli", "gwmgr", "gwsvr", "gwmon", "gwadm",
            # OFGW 기능
            "webterminal", "web terminal",
            # 설정
            "ofgw.conf", "gw.conf",
        ],
        patterns=[
            r"ofgw\s+\w+",
            r"gwmgr\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFMANAGER,
        keywords=[
            "ofmanager", "openframe manager", "of manager",
            "ofmgr", "webmanager",
            # OFManager 기능
            "batch monitor", "job monitor",
            "resource manager", "system monitor",
            "log viewer", "config editor",
        ],
        patterns=[
            r"ofmanager\s+\w+",
            r"ofm_\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFMINER,
        keywords=[
            "ofminer", "openframe miner", "of miner",
            "migration analysis", "impact analysis",
            "call tree", "cross reference", "xref",
            "dead code", "complexity",
        ],
        patterns=[
            r"ofminer\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.OFSTUDIO,
        keywords=[
            "ofstudio", "openframe studio", "of studio",
            "dataset editor", "jcl editor",
            "cobol editor", "bms editor",
            "map editor", "region manager",
        ],
        patterns=[
            r"ofstudio\s+\w+",
            r"openframe\s+studio",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.PROSORT,
        keywords=[
            "prosort",
            # ProSort 명령어
            "inrec", "outrec", "outfil",
            "sortin", "sortout",
            # ProSort 기능
            "include", "omit",
            # 설정
            "prosort.cfg", "prosort.conf",
        ],
        patterns=[
            r"prosort\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.PROSYNC,
        keywords=[
            "prosync",
            "syncmgr",
            "change data capture", "cdc",
            "replication",
            # 설정
            "prosync.conf",
        ],
        patterns=[
            r"prosync\s+\w+",
        ],
        weight=1.0
    ),
    ProductConfig(
        product=ProductId.PROTRIEVE,
        keywords=[
            "protrieve", "easytrieve", "eztrieve",
            "report generator",
            # 설정
            "protrieve.conf",
        ],
        patterns=[
            r"protrieve\s+\w+",
            r"easytrieve\s+\w+",
        ],
        weight=1.0
    ),
]

# Pre-compile patterns
for config in PRODUCT_CONFIGS:
    config._compiled_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.patterns
    ]


class ProductRouterService:
    """
    Product Router Service

    쿼리를 분석하여 적절한 제품으로 라우팅합니다.
    키워드 매칭 및 패턴 매칭을 통해 confidence 점수를 계산합니다.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.7,
        min_keyword_matches: int = 1,
    ):
        """
        Initialize service

        Args:
            confidence_threshold: 자동 라우팅을 위한 최소 confidence (기본: 0.7)
            min_keyword_matches: 최소 매칭 키워드 수 (기본: 1)
        """
        self.confidence_threshold = confidence_threshold
        self.min_keyword_matches = min_keyword_matches
        self.product_configs = PRODUCT_CONFIGS

    def classify(self, query: str) -> ClassificationResult:
        """
        쿼리를 분석하여 제품 분류 결과 반환

        Args:
            query: 사용자 쿼리

        Returns:
            ClassificationResult with product, confidence, and suggestions
        """
        query_lower = query.lower()
        scores: Dict[ProductId, float] = {}
        matched_keywords: Dict[ProductId, List[str]] = {}

        for config in self.product_configs:
            score, matches = self._calculate_score(query_lower, config)
            if score > 0:
                scores[config.product] = score
                matched_keywords[config.product] = matches

        # Sort by score
        sorted_products = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_products:
            # No matches found
            return ClassificationResult(
                product=ProductId.OTHER,
                confidence=0.0,
                needs_selection=True,
                suggestions=[ProductId.OPENFRAME_MVS.value],  # Default suggestion
                matched_keywords=[],
                all_scores={},
            )

        # Get top result
        top_product, top_score = sorted_products[0]

        # Normalize score to 0-1 range
        # Typical strong match: 3-5 keywords (0.3-0.5) + 1-2 patterns (0.2-0.4) + bonus (1.2) ≈ 0.6-1.2
        max_score = 1.5
        confidence = min(top_score / max_score, 1.0)

        # Determine if user selection is needed
        needs_selection = confidence < self.confidence_threshold

        # Get suggestions (top 3 products)
        suggestions = [p.value for p, _ in sorted_products[:3]]

        # All scores for transparency
        all_scores = {p.value: round(s / max_score, 3) for p, s in scores.items()}

        return ClassificationResult(
            product=top_product,
            confidence=round(confidence, 3),
            needs_selection=needs_selection,
            suggestions=suggestions,
            matched_keywords=matched_keywords.get(top_product, []),
            all_scores=all_scores,
        )

    def _calculate_score(
        self,
        query_lower: str,
        config: ProductConfig
    ) -> Tuple[float, List[str]]:
        """
        Calculate score for a product

        Args:
            query_lower: Lowercase query
            config: Product configuration

        Returns:
            (score, matched_keywords)
        """
        score = 0.0
        matched = []

        # Keyword matching — 英単語は単語境界マッチ (例: "asm"が"mscasmc"にマッチしない)
        for keyword in config.keywords:
            kw = keyword.lower()
            if not re.search(rf'(?<![a-z0-9_/]){re.escape(kw)}(?![a-z0-9_])', query_lower):
                continue
            score += 0.15 * config.weight
            matched.append(keyword)

        # Pattern matching (higher weight)
        for pattern in getattr(config, '_compiled_patterns', []):
            if pattern.search(query_lower):
                score += 0.3 * config.weight
                matched.append(f"pattern:{pattern.pattern[:20]}")

        # Bonus for multiple matches
        if len(matched) >= 3:
            score *= 1.2
        elif len(matched) >= 2:
            score *= 1.1

        return score, matched

    def get_product_keywords(self, product: ProductId) -> List[str]:
        """Get keywords for a specific product"""
        for config in self.product_configs:
            if config.product == product:
                return config.keywords
        return []

    def get_all_products(self) -> List[ProductId]:
        """Get all supported products"""
        return [config.product for config in self.product_configs]


# =============================================================================
# Singleton Instance
# =============================================================================

_product_router_service: Optional[ProductRouterService] = None


def get_product_router_service() -> ProductRouterService:
    """Get Product Router service singleton"""
    global _product_router_service
    if _product_router_service is None:
        _product_router_service = ProductRouterService()
    return _product_router_service
