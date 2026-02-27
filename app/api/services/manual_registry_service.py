"""
Manual Registry Service

uploads/manuals/ 디렉토리를 스캔하여 제품/버전/언어를 자동 발견하는 서비스.
하드코딩된 ProductId enum 대신 파일 시스템 기반 동적 제품 목록을 제공합니다.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 프로젝트 루트 기준 매뉴얼 경로
MANUALS_BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "uploads", "manuals",
)


@dataclass
class ManualVersion:
    """제품 매뉴얼 버전 정보"""
    product_id: str        # "jeus_8.5" (normalized, unique key)
    family: str            # "JEUS" (grouping key)
    display_name: str      # "JEUS 8.5"
    version: str           # "8.5"
    doc_version: str       # "v2.1.1"
    language: str          # "KR"
    directory_name: str    # "JEUS_8.5_v2.1.1_KR"
    directory_path: str    # Full absolute path
    pdf_files: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


class ManualRegistryService:
    """
    파일 시스템 기반 제품 레지스트리

    uploads/manuals/ 하위 디렉토리를 스캔하여
    제품명, 버전, 문서 버전, 언어를 자동 추출합니다.
    """

    # 디렉토리명 파싱 패턴 (우선순위 순서)
    _PATTERNS = [
        # Standard: JEUS_8.5_v2.1.1_KR, OFCOBOL_4_v3.1.2_JP
        re.compile(
            r'^(.+?)_([\d.]+(?:Fix\d+|SP\d+)?)_v([\d.]+)_([A-Za-z]{2})$'
        ),
        # Openframe with space: MVS_Openframe 7.1_v3.1.3_JP
        re.compile(
            r'^(.+?)_[Oo]penframe\s+([\d.]+)\s*_\s*v([\d.]+)\s*_\s*([A-Za-z]{2})$'
        ),
        # Tibero special: Tibero 7 FixSet01 Manual Set v2.1.1_jp
        re.compile(
            r'^(Tibero)\s+(\d+(?:\s+FixSet\d+)?)\s+Manual\s+Set\s+v([\d.]+)_([A-Za-z]{2})$',
            re.IGNORECASE,
        ),
        # VOS3 with spaces: VOS3_Openframe 2.0 _v2.1.1 _JP
        re.compile(
            r'^(.+?)_[Oo]penframe\s+([\d.]+)\s+_v([\d.]+)\s+_([A-Za-z]{2})$'
        ),
        # No doc_version: ProSync_FS01_JP
        re.compile(
            r'^(.+?)_([\w.]+)_([A-Za-z]{2})$'
        ),
    ]

    # 제품 패밀리 정규화 매핑
    _FAMILY_NORMALIZE = {
        "mvs": "MVS OpenFrame",
        "msp": "MSP OpenFrame",
        "vos3": "VOS3 OpenFrame",
        "xsp": "XSP OpenFrame",
        "ofasm": "OFASM",
        "ofcobol": "OFCOBOL",
        "ofgw": "OFGW",
        "ofmanager": "OFManager",
        "ofminer": "OFMiner",
        "ofpli": "OFPli",
        "ofstudio": "OFStudio",
        "jeus": "JEUS",
        "tibero": "Tibero",
        "tmax": "Tmax",
        "webtob": "WebtoB",
        "prosort": "ProSort",
        "prosync": "ProSync",
        "protrieve": "ProTrieve",
    }

    # 제품별 라우팅 키워드 (검색용)
    _ROUTING_KEYWORDS: Dict[str, List[str]] = {
        "mvs": ["mvs", "openframe", "tjes", "tjesmgr", "tacf", "tacfmgr", "osc", "oscmgr",
                 "batch", "jcl", "dataset", "hidb", "hidbmgr", "osi", "osimgr",
                 "mscasmc", "mscmapc", "mscmapupdate", "dfhmdf", "dfhmdi", "dfhmsd"],
        "msp": ["msp", "jes2", "jes3", "sms", "hsm", "aim"],
        "vos3": ["vos3", "acos", "nec"],
        "xsp": ["xsp"],
        "jeus": ["jeus", "was", "weblogic", "servlet", "jsp", "ejb", "jndi", "jdbc"],
        "tibero": ["tibero", "tbsql", "database", "rdbms", "sql",
                   "dbms_lock", "dbms_output", "dbms_sql", "dbms_job", "dbms_",
                   "tbpsm", "psm", "package", "パッケージ"],
        "tmax": ["tmax", "tuxedo", "tp monitor", "middleware"],
        "webtob": ["webtob", "web server", "http", "reverse proxy"],
        "ofasm": ["ofasm", "assembler", "asm", "hlasm"],
        "ofcobol": ["ofcobol", "cobol"],
        "ofgw": ["ofgw", "gateway"],
        "ofmanager": ["ofmanager", "manager", "console"],
        "ofminer": ["ofminer", "miner", "analysis"],
        "ofpli": ["ofpli", "pli", "pl/i"],
        "ofstudio": ["ofstudio", "studio", "ide"],
        "prosort": ["prosort", "sort", "dfsort", "syncsort"],
        "prosync": ["prosync", "sync", "replication"],
        "protrieve": ["protrieve", "trieve", "retrieve"],
    }

    def __init__(self, manuals_base: Optional[str] = None):
        self._manuals_base = manuals_base or MANUALS_BASE
        self._products: Dict[str, ManualVersion] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._scan_directories()
        self._loaded = True

    def _scan_directories(self):
        """uploads/manuals/ 하위 디렉토리 스캔"""
        if not os.path.isdir(self._manuals_base):
            logger.warning(f"Manuals directory not found: {self._manuals_base}")
            return

        for dir_name in sorted(os.listdir(self._manuals_base)):
            dir_path = os.path.join(self._manuals_base, dir_name)
            if not os.path.isdir(dir_path):
                continue

            product = self._parse_directory_name(dir_name, dir_path)
            if product:
                # PDF 파일 목록 수집
                product.pdf_files = sorted([
                    f for f in os.listdir(dir_path)
                    if f.lower().endswith('.pdf')
                ])
                # 키워드 추론
                product.keywords = self._infer_keywords(product)
                self._products[product.product_id] = product

        logger.info(
            f"ManualRegistry: discovered {len(self._products)} products "
            f"from {self._manuals_base}"
        )

    def _parse_directory_name(self, name: str, dir_path: str) -> Optional[ManualVersion]:
        """디렉토리명에서 제품 정보 파싱"""
        for pattern in self._PATTERNS:
            m = pattern.match(name)
            if m:
                groups = m.groups()
                if len(groups) == 4:
                    raw_family, version, doc_version, language = groups
                elif len(groups) == 3:
                    # No doc_version 패턴
                    raw_family, version, language = groups
                    doc_version = ""
                else:
                    continue

                family = self._normalize_family(raw_family)
                product_id = self._make_product_id(family, version)
                display_name = f"{family} {version}".strip()

                return ManualVersion(
                    product_id=product_id,
                    family=family,
                    display_name=display_name,
                    version=version,
                    doc_version=doc_version,
                    language=language.upper(),
                    directory_name=name,
                    directory_path=dir_path,
                )

        # Fallback: 디렉토리명을 slug화
        logger.warning(f"Could not parse directory name: {name}, using fallback")
        slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        return ManualVersion(
            product_id=slug,
            family=name.split('_')[0] if '_' in name else name,
            display_name=name,
            version="",
            doc_version="",
            language="",
            directory_name=name,
            directory_path=dir_path,
        )

    def _normalize_family(self, raw: str) -> str:
        """제품명 정규화"""
        # 언더스코어/공백 정리
        key = raw.replace('_', '').replace(' ', '').lower()
        # 매핑 테이블에서 찾기
        for prefix, normalized in self._FAMILY_NORMALIZE.items():
            if key.startswith(prefix) or prefix.startswith(key):
                return normalized
        # 없으면 원본 정리
        return raw.replace('_', ' ').strip()

    def _make_product_id(self, family: str, version: str) -> str:
        """product_id 생성: {family_lower}_{version}"""
        family_slug = re.sub(r'[^a-z0-9]+', '_', family.lower()).strip('_')
        version_slug = re.sub(r'[^a-z0-9.]+', '', version.lower())
        if version_slug:
            return f"{family_slug}_{version_slug}"
        return family_slug

    def _infer_keywords(self, product: ManualVersion) -> List[str]:
        """제품에서 라우팅 키워드 추론"""
        keywords: List[str] = []
        family_lower = product.family.lower()

        # 패밀리명에서 키워드 매칭
        for key, kw_list in self._ROUTING_KEYWORDS.items():
            if key in family_lower or family_lower.startswith(key):
                keywords.extend(kw_list)
                break

        # 기본 키워드: 패밀리명과 product_id
        if product.family.lower() not in keywords:
            keywords.append(product.family.lower())
        if product.product_id not in keywords:
            keywords.append(product.product_id)

        # PDF 파일명에서 추가 키워드 추출
        for pdf in product.pdf_files[:5]:
            # PDF 파일명에서 의미 있는 단어 추출
            name_parts = re.sub(r'[_\-.]', ' ', pdf.replace('.pdf', '')).split()
            for part in name_parts:
                part_lower = part.lower()
                if len(part_lower) >= 3 and part_lower not in keywords:
                    keywords.append(part_lower)

        return list(dict.fromkeys(keywords))  # 순서 유지하며 중복 제거

    # =========================================================================
    # Public API
    # =========================================================================

    def get_product(self, product_id: str) -> Optional[ManualVersion]:
        """product_id로 제품 조회"""
        self._ensure_loaded()
        return self._products.get(product_id)

    def get_all_products(self) -> Dict[str, ManualVersion]:
        """전체 제품 목록"""
        self._ensure_loaded()
        return dict(self._products)

    def get_product_groups(self) -> Dict[str, List[ManualVersion]]:
        """패밀리별 그룹핑된 제품 목록"""
        self._ensure_loaded()
        groups: Dict[str, List[ManualVersion]] = {}
        for product in self._products.values():
            if product.family not in groups:
                groups[product.family] = []
            groups[product.family].append(product)
        # 각 그룹 내 버전 정렬
        for versions in groups.values():
            versions.sort(key=lambda v: v.version, reverse=True)
        return groups

    def get_routing_patterns(self) -> List[Tuple[str, str]]:
        """
        라우팅 패턴 목록 반환: [(regex_pattern, product_id), ...]
        QueryRouter에서 쿼리→제품 매칭에 사용
        """
        self._ensure_loaded()
        patterns: List[Tuple[str, str]] = []
        for product in self._products.values():
            for kw in product.keywords:
                # 영문 키워드만 패턴화 (일본어/한국어 키워드는 직접 매칭)
                if re.match(r'^[a-z0-9_/. ]+$', kw):
                    escaped = re.escape(kw)
                    patterns.append((rf'\b{escaped}\b', product.product_id))
        return patterns

    def find_product_by_keyword(self, keyword: str) -> Optional[str]:
        """키워드로 product_id 찾기"""
        self._ensure_loaded()
        keyword_lower = keyword.lower()
        for product in self._products.values():
            if keyword_lower in product.keywords:
                return product.product_id
        return None


# =============================================================================
# Singleton
# =============================================================================

_instance: Optional[ManualRegistryService] = None


def get_manual_registry_service() -> ManualRegistryService:
    """Get singleton ManualRegistryService"""
    global _instance
    if _instance is None:
        _instance = ManualRegistryService()
    return _instance
