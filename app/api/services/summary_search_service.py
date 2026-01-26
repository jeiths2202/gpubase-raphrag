"""
매뉴얼 요약본 검색 서비스

Two-Stage Retrieval의 1단계를 담당합니다.
파일 시스템 기반으로 요약본에서 빠르게 컨텍스트를 추출합니다.
"""

import re
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class SummarySearchService:
    """매뉴얼 요약본 검색 서비스

    에러 코드, 용어 등을 요약본에서 빠르게 검색하여
    RAG 쿼리를 보강하는 컨텍스트를 제공합니다.
    """

    def __init__(self, summaries_dir: Optional[Path] = None):
        self.summaries_dir = summaries_dir or Path("/opt/kms/uploads/summaries")
        self.error_codes_dir = self.summaries_dir / "error-codes"
        self.glossary_dir = self.summaries_dir / "glossary"
        self.commands_dir = self.summaries_dir / "commands"
        self.configs_dir = self.summaries_dir / "configs"
        self.concepts_dir = self.summaries_dir / "concepts"
        self._index_cache: Optional[Dict] = None

    def _load_index(self) -> Dict:
        """인덱스 로드 (캐싱)"""
        if self._index_cache is not None:
            return self._index_cache

        index_path = self.summaries_dir / "index.json"
        if index_path.exists():
            try:
                self._index_cache = json.loads(index_path.read_text(encoding="utf-8"))
                return self._index_cache
            except Exception as e:
                logger.warning(f"인덱스 로드 실패: {e}")

        return {}

    async def search_error_code(self, code: str) -> Optional[Dict[str, Any]]:
        """에러 코드 검색

        Args:
            code: 에러 코드 (예: "-5212", "5212")

        Returns:
            에러 정보 딕셔너리 또는 None
        """
        # 숫자만 추출
        code_num = re.sub(r"[^0-9]", "", code)
        if not code_num:
            return None

        code_int = int(code_num)

        # 모듈 범위 매핑
        module_ranges = {
            (0, 999): "BASE-0.md",
            (1000, 1999): "BASE-1000.md",
            (2000, 2999): "BASE-2000.md",
            (3000, 3999): "BASE-3000.md",
            (4000, 4999): "BASE-4000.md",
            (5000, 5999): "BASE-5000.md",
            (6000, 6999): "BASE-6000.md",
            (7000, 7999): "BASE-7000.md",
            (8000, 8999): "BASE-8000.md",
            (9000, 9999): "BATCH-9000.md",
            (10000, 10999): "BASE-10000.md",
            (11000, 11999): "BASE-11000.md",
            (12000, 12999): "BASE-12000.md",
            (13000, 13999): "BATCH-13000.md",
            (15000, 15999): "BASE-15000.md",
            (16000, 16999): "BATCH-16000.md",
            (17000, 17999): "BASE-17000.md",
            (18000, 18999): "TACF-18000.md",
            (21000, 21999): "AIM-21000.md",
            (22000, 22999): "BASE-22000.md",
            (32000, 32999): "BASE-32000.md",
            (34000, 34499): "BASE-34000.md",
            (34500, 34999): "BASE-34500.md",
            (36000, 36999): "BASE-36000.md",
            (38000, 38999): "NDB-38000.md",
            (80000, 80999): "AIM-80000.md",
            (82000, 82999): "AIM-82000.md",
            (84000, 84999): "AIM-84000.md",
            (85000, 85999): "AIM-85000.md",
            (86000, 86999): "AIM-86000.md",
            (87000, 87999): "AIM-87000.md",
            (88000, 88999): "AIM-88000.md",
            (89000, 89999): "AIM-89000.md",
            (92000, 92999): "BATCH-92000.md",
            (93000, 93999): "BASE-93000.md",
            (99000, 99999): "NDB-99000.md",
        }

        # 적합한 파일 찾기
        target_file = None
        for (start, end), filename in module_ranges.items():
            if start <= code_int <= end:
                target_file = self.error_codes_dir / filename
                break

        if not target_file or not target_file.exists():
            # 대체: 모든 에러 파일에서 검색
            return await self._search_all_error_files(code_num)

        # 파일에서 에러 코드 검색
        return self._parse_error_from_file(target_file, code_num)

    def _parse_error_from_file(self, file_path: Path, code: str) -> Optional[Dict[str, Any]]:
        """파일에서 에러 코드 파싱"""
        try:
            content = file_path.read_text(encoding="utf-8")

            # 에러 코드 패턴: ### ERROR_NAME (-1234)
            pattern = rf"### ([A-Z_]+) \(-?{code}\)\n(.*?)(?=### [A-Z_]+|\Z)"
            match = re.search(pattern, content, re.DOTALL)

            if match:
                name = match.group(1)
                details = match.group(2)

                # 설명, 대처방법 추출
                desc_match = re.search(r"\*\*설명\*\*: (.+?)(?=\n-|\Z)", details)
                sol_match = re.search(r"\*\*대처방법\*\*: (.+?)(?=\n-|\Z)", details)

                # 모듈 정보 (파일명에서)
                module_match = re.search(r"module: (\w+)", content)
                module = module_match.group(1) if module_match else ""

                return {
                    "code": f"-{code}",
                    "name": name,
                    "module": module,
                    "description": desc_match.group(1).strip() if desc_match else "",
                    "solution": sol_match.group(1).strip() if sol_match else "",
                    "source_file": file_path.name,
                }

        except Exception as e:
            logger.warning(f"에러 파일 파싱 실패: {file_path} - {e}")

        return None

    async def _search_all_error_files(self, code: str) -> Optional[Dict[str, Any]]:
        """모든 에러 파일에서 검색 (폴백)"""
        if not self.error_codes_dir.exists():
            return None

        for file_path in self.error_codes_dir.glob("*.md"):
            if file_path.name == "index.md":
                continue
            result = self._parse_error_from_file(file_path, code)
            if result:
                return result

        return None

    async def search_command(self, cmd: str) -> Optional[Dict[str, Any]]:
        """명령어/유틸리티 검색 (모든 제품 버전 반환)

        Args:
            cmd: 명령어 이름 (예: "tjesinit", "oscboot")

        Returns:
            명령어 정보 딕셔너리 (products 배열 포함) 또는 None
        """
        if not cmd or not self.commands_dir.exists():
            return None

        # 첫 글자로 파일 결정
        first_letter = cmd[0].upper()
        if not first_letter.isalpha():
            first_letter = "OTHER"

        cmd_file = self.commands_dir / f"{first_letter}.md"
        if not cmd_file.exists():
            return None

        try:
            content = cmd_file.read_text(encoding="utf-8")

            # 명령어 섹션 전체 추출 (## cmd 부터 다음 ## 까지)
            pattern = rf"## {re.escape(cmd)}\n(.*?)(?=\n## [a-zA-Z]|\Z)"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if match:
                details = match.group(1)

                # 지원 제품 추출 (새 형식: **지원 제품**: ...)
                products_match = re.search(r"\*\*지원 제품\*\*:\s*(.+?)(?:\n|$)", details)
                products = []
                if products_match:
                    products = [p.strip() for p in products_match.group(1).split(",")]

                # 제품별 정보 추출 (### OpenFrame XXX 또는 ### Tmax 등)
                product_sections = re.findall(
                    r"###\s+(OpenFrame\s+\w+|Tibero|Tmax|WebT|OFManager)\s*\n(.*?)(?=###\s+|$)",
                    details, re.DOTALL
                )

                if product_sections:
                    # 여러 제품 버전이 있는 경우
                    product_info = []
                    for product, section in product_sections:
                        desc_match = re.search(r"\*\*설명\*\*:\s*(.+?)(?:\n-|\n\*\*|$)", section, re.DOTALL)
                        syntax_match = re.search(r"\*\*구문\*\*:\s*`(.+?)`", section, re.DOTALL)
                        ref_match = re.search(r"\*\*참조\*\*:\s*(.+?)(?:\n|$)", section)

                        description = ""
                        if desc_match:
                            # 설명에서 줄바꿈을 공백으로 치환하고 정리
                            description = ' '.join(desc_match.group(1).strip().split())

                        product_info.append({
                            "product": product.strip(),
                            "description": description[:300],
                            "syntax": syntax_match.group(1).strip() if syntax_match else "",
                            "reference": ref_match.group(1).strip() if ref_match else "",
                        })

                    return {
                        "command": cmd.lower(),
                        "products": products or [p["product"] for p in product_info],
                        "multi_product": len(product_info) > 1,
                        "product_info": product_info,
                        "source_file": cmd_file.name,
                    }
                else:
                    # 단일 제품인 경우 (제품 섹션 없음)
                    # 지원 제품이 하나만 있는 경우
                    desc_match = re.search(r"\*\*설명\*\*:\s*(.+?)(?:\n-|\n\*\*|$)", details, re.DOTALL)
                    syntax_match = re.search(r"\*\*구문\*\*:\s*`(.+?)`", details, re.DOTALL)
                    ref_match = re.search(r"\*\*참조\*\*:\s*(.+?)(?:\n|$)", details)

                    description = ""
                    if desc_match:
                        description = ' '.join(desc_match.group(1).strip().split())

                    return {
                        "command": cmd.lower(),
                        "products": products,
                        "multi_product": len(products) > 1,
                        "description": description[:300],
                        "syntax": syntax_match.group(1).strip() if syntax_match else "",
                        "reference": ref_match.group(1).strip() if ref_match else "",
                        "source_file": cmd_file.name,
                    }

        except Exception as e:
            logger.warning(f"명령어 파일 파싱 실패: {cmd_file} - {e}")

        return None

    async def _search_all_commands(self, cmd: str) -> Optional[Dict[str, Any]]:
        """모든 명령어 파일에서 검색 (폴백)"""
        if not self.commands_dir.exists():
            return None

        for file_path in self.commands_dir.glob("*.md"):
            if file_path.name == "index.md":
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                pattern = rf"## {re.escape(cmd)}\n"
                if re.search(pattern, content, re.IGNORECASE):
                    return await self.search_command(cmd)
            except:
                pass

        return None

    async def search_glossary(self, term: str) -> Optional[Dict[str, Any]]:
        """용어 검색

        Args:
            term: 검색할 용어 (예: "TJES", "TACF")

        Returns:
            용어 정보 딕셔너리 또는 None
        """
        if not term or not self.glossary_dir.exists():
            return None

        # 첫 글자로 파일 결정
        first_letter = term[0].upper()
        if not first_letter.isalpha():
            first_letter = "OTHER"

        glossary_file = self.glossary_dir / f"{first_letter}.md"
        if not glossary_file.exists():
            return None

        try:
            content = glossary_file.read_text(encoding="utf-8")

            # 용어 패턴: ## TERM_NAME
            pattern = rf"## {re.escape(term)}\n(.*?)(?=## [A-Z]|\Z)"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if match:
                details = match.group(1)

                # 정식명칭, 설명 추출
                full_name_match = re.search(r"\*\*정식명칭\*\*: (.+?)(?=\n|\Z)", details)
                desc_match = re.search(r"\*\*설명\*\*: (.+?)(?=\n-|\Z)", details)
                product_match = re.search(r"\*\*제품군\*\*: (.+?)(?=\n|\Z)", details)

                return {
                    "term": term.upper(),
                    "full_name": full_name_match.group(1).strip() if full_name_match else "",
                    "description": desc_match.group(1).strip() if desc_match else "",
                    "product": product_match.group(1).strip() if product_match else "",
                    "source_file": glossary_file.name,
                }

        except Exception as e:
            logger.warning(f"용어 파일 파싱 실패: {glossary_file} - {e}")

        return None

    async def enrich_query(self, query: str) -> str:
        """쿼리 보강

        사용자 쿼리에서 에러 코드와 기술 용어를 감지하여
        컨텍스트 정보로 보강합니다.

        Args:
            query: 원본 사용자 쿼리

        Returns:
            보강된 쿼리 문자열
        """
        enrichments = []

        # 1. 에러 코드 감지 (-5212, 5212 등)
        error_codes = re.findall(r"-?\d{4,5}", query)
        for code in error_codes[:3]:  # 최대 3개
            result = await self.search_error_code(code)
            if result:
                enrichments.append(
                    f"[에러 {result['code']}: {result['module']} - {result['name']}]"
                )

        # 2. 기술 용어 감지 (대문자 약어)
        terms = re.findall(r"\b[A-Z]{2,}[A-Z0-9]*\b", query)
        seen_terms = set()
        for term in terms[:5]:  # 최대 5개
            if term in seen_terms:
                continue
            seen_terms.add(term)

            result = await self.search_glossary(term)
            if result and result.get("full_name"):
                enrichments.append(
                    f"[{term}: {result['full_name']}]"
                )

        # 보강 정보가 있으면 쿼리에 추가
        if enrichments:
            context = " ".join(enrichments)
            return f"{query}\n\n컨텍스트: {context}"

        return query

    async def get_error_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 에러 컨텍스트 생성

        RAG Agent가 사용할 수 있는 형식으로 에러 정보를 제공합니다.
        """
        error_codes = re.findall(r"-?\d{4,5}", query)
        if not error_codes:
            return None

        contexts = []
        for code in error_codes[:2]:
            result = await self.search_error_code(code)
            if result:
                contexts.append(
                    f"에러코드 {result['code']} ({result['module']}/{result['name']}):\n"
                    f"  설명: {result['description']}\n"
                    f"  대처: {result['solution']}"
                )

        return "\n\n".join(contexts) if contexts else None

    async def get_term_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 용어 컨텍스트 생성"""
        terms = re.findall(r"\b[A-Z]{2,}[A-Z0-9]*\b", query)
        if not terms:
            return None

        contexts = []
        seen = set()
        for term in terms[:3]:
            if term in seen:
                continue
            seen.add(term)

            result = await self.search_glossary(term)
            if result and result.get("full_name"):
                contexts.append(
                    f"{term} ({result['full_name']}): {result['description'][:100]}..."
                    if len(result.get('description', '')) > 100
                    else f"{term} ({result['full_name']}): {result.get('description', '')}"
                )

        return "\n".join(contexts) if contexts else None

    async def get_command_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 명령어 컨텍스트 생성

        소문자 명령어 패턴 감지 (tjesinit, oscboot 등)
        여러 제품에서 동일 명령어가 있으면 모두 표시하고 사용자에게 확인 요청
        """
        # 소문자 명령어 패턴 감지
        cmd_patterns = [
            r"\b([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b",
            r"\b(tjes\w+|osc\w+|tac\w+|ofm\w+)\b",  # OF 계열 명령어
            r"([a-z][a-z0-9_-]{3,})(?:이|가|을|를|에|의|란|뭐|무엇)",  # 한국어 질문 패턴
        ]

        commands = []
        for pattern in cmd_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            commands.extend(matches)

        if not commands:
            return None

        contexts = []
        seen = set()
        for cmd in commands[:3]:
            cmd_lower = cmd.lower()
            if cmd_lower in seen:
                continue
            seen.add(cmd_lower)

            result = await self.search_command(cmd_lower)
            if not result:
                # 전체 검색 시도
                result = await self._search_all_commands(cmd_lower)

            if result:
                ctx = self._format_command_context(result)
                contexts.append(ctx)

        return "\n\n".join(contexts) if contexts else None

    def _format_command_context(self, result: Dict[str, Any]) -> str:
        """명령어 컨텍스트 포맷팅 (멀티 제품 지원)"""
        cmd = result['command']
        products = result.get('products', [])

        if result.get('multi_product') and len(products) > 1:
            # 여러 제품에 동일 명령어가 있는 경우
            ctx = f"명령어 '{cmd}'은 여러 OpenFrame 제품에서 사용됩니다:\n"
            ctx += f"- 지원 제품: {', '.join(products)}\n\n"

            for info in result.get('product_info', []):
                product = info.get('product', '')
                desc = info.get('description', '')
                ref = info.get('reference', '')
                ctx += f"[{product}]\n"
                if desc:
                    ctx += f"  설명: {desc[:200]}\n"
                if ref:
                    ctx += f"  참조: {ref}\n"

            ctx += "\n⚠️ 사용자에게 어떤 제품(MSP/MVS/VOS3/XSP)에 대한 정보가 필요한지 확인하세요."
            return ctx
        else:
            # 단일 제품
            ctx = f"명령어 {cmd}"
            if products:
                ctx += f" ({products[0]})"
            desc = result.get('description', '')
            if desc:
                ctx += f": {desc[:150]}"
            if result.get('syntax'):
                ctx += f"\n  구문: {result['syntax']}"
            return ctx

    async def search_api(self, api_name: str) -> Optional[Dict[str, Any]]:
        """API 함수 검색 (tcfh_*, tfcd_*, tdcb_* 등)

        Args:
            api_name: API 함수 이름 (예: "tcfh_stow", "tfcd_read")

        Returns:
            API 정보 딕셔너리 또는 None
        """
        apis_dir = self.summaries_dir / "apis"
        if not api_name or not apis_dir.exists():
            return None

        # 모든 API 파일 검색
        for api_file in apis_dir.glob("*.md"):
            if api_file.name == "index.md":
                continue

            try:
                content = api_file.read_text(encoding="utf-8")

                # API 함수 패턴 검색: ## api_name
                pattern = rf"## {re.escape(api_name)}\s*(?:\(\))?\n(.*?)(?=\n## |\Z)"
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

                if match:
                    details = match.group(1)

                    product_match = re.search(r"\*\*제품\*\*:\s*(.+?)(?:\n|$)", details)
                    desc_match = re.search(r"\*\*설명\*\*:\s*(.+?)(?:\n-|\n\*\*|$)", details, re.DOTALL)
                    syntax_match = re.search(r"\*\*(?:구문|프로토타입)\*\*:\s*`(.+?)`", details, re.DOTALL)
                    ref_match = re.search(r"\*\*참조\*\*:\s*(.+?)(?:\n|$)", details)

                    description = ""
                    if desc_match:
                        description = ' '.join(desc_match.group(1).strip().split())

                    return {
                        "api": api_name,
                        "product": product_match.group(1).strip() if product_match else "",
                        "description": description[:300],
                        "syntax": syntax_match.group(1).strip() if syntax_match else "",
                        "reference": ref_match.group(1).strip() if ref_match else "",
                        "source_file": api_file.name,
                    }

            except Exception as e:
                logger.debug(f"API 파일 파싱 실패: {api_file} - {e}")

        return None

    async def get_api_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 API 컨텍스트 생성

        OpenFrame API 함수 패턴 감지 (tcfh_*, tfcd_*, tdcb_* 등)
        """
        # API 함수 패턴 감지 (한글과 함께 사용 시 \b 대신 (?:^|[^a-z_]) 사용)
        api_patterns = [
            r"(?:^|[^a-z_])(tcfh_[a-z_]+)",      # tcfh_* (Dataset I/O)
            r"(?:^|[^a-z_])(tfcd_[a-z_]+)",      # tfcd_* (Record Access)
            r"(?:^|[^a-z_])(tdcb_[a-z_]+)",      # tdcb_* (DCB Handling)
            r"(?:^|[^a-z_])(tpam_[a-z_]+)",      # tpam_* (PAM)
            r"(?:^|[^a-z_])([a-z]{2,4}_[a-z_]+)\s*\(\)",  # xxx_yyy() 형식
        ]

        apis = []
        for pattern in api_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            apis.extend(matches)

        if not apis:
            return None

        contexts = []
        seen = set()
        for api in apis[:3]:
            api_lower = api.lower().rstrip('()')
            if api_lower in seen:
                continue
            seen.add(api_lower)

            result = await self.search_api(api_lower)
            if result:
                ctx = f"API 함수 {result['api']}"
                if result.get('product'):
                    ctx += f" ({result['product']})"
                if result.get('description'):
                    ctx += f": {result['description'][:200]}"
                if result.get('syntax'):
                    ctx += f"\n  프로토타입: {result['syntax']}"
                if result.get('reference'):
                    ctx += f"\n  참조: {result['reference']}"
                contexts.append(ctx)

        return "\n\n".join(contexts) if contexts else None

    async def search_product(self, product_name: str) -> Optional[Dict[str, Any]]:
        """제품 정보 검색

        Args:
            product_name: 제품명 (예: "OpenFrame Base", "OpenFrame Batch", "TACF")

        Returns:
            제품 정보 (APIs, commands, configs 개수 및 목록)
        """
        # 제품명 정규화
        product_lower = product_name.lower().strip()

        # 제품명 매핑
        product_map = {
            "base": "OpenFrame_Base",
            "openframe base": "OpenFrame_Base",
            "batch": "OpenFrame_Batch",
            "openframe batch": "OpenFrame_Batch",
            "common": "OpenFrame_Common",
            "openframe common": "OpenFrame_Common",
            "tacf": "OpenFrame_TACF",
            "openframe tacf": "OpenFrame_TACF",
            "osc": "OpenFrame_OSC",
            "openframe osc": "OpenFrame_OSC",
            "osi": "OpenFrame_OSI",
            "openframe osi": "OpenFrame_OSI",
            "tjes": "OpenFrame_TJES",
            "openframe tjes": "OpenFrame_TJES",
            "hidb": "OpenFrame_HiDB",
            "openframe hidb": "OpenFrame_HiDB",
            "tmax": "Tmax",
            "tibero": "Tibero",
        }

        # 제품명 찾기
        product_key = None
        for key, value in product_map.items():
            if key in product_lower:
                product_key = value
                break

        if not product_key:
            return None

        result = {
            "product": product_key.replace("_", " "),
            "apis": [],
            "commands": [],
            "configs": [],
            "api_count": 0,
            "command_count": 0,
            "config_count": 0,
        }

        # API 파일 검색
        apis_dir = self.summaries_dir / "apis"
        api_file = apis_dir / f"{product_key}.md"
        if api_file.exists():
            try:
                content = api_file.read_text(encoding="utf-8")
                # API 목록 추출
                apis = re.findall(r"^## ([a-zA-Z_][a-zA-Z0-9_]*)", content, re.MULTILINE)
                result["apis"] = apis[:20]  # 상위 20개
                result["api_count"] = len(apis)
            except Exception as e:
                logger.debug(f"API 파일 읽기 실패: {e}")

        # 명령어 검색 (index.json에서)
        index = self._load_index()
        items = index.get("items", index)  # items 키가 있으면 사용, 없으면 전체 사용
        commands = []
        product_search = product_key.replace("_", " ")
        for cmd_name, entries in items.items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, dict):
                        # product 또는 products 필드 확인
                        entry_product = entry.get("product", "")
                        entry_products = entry.get("products", [])
                        entry_type = entry.get("type", "")
                        # 명령어 타입이고 제품이 일치하면 추가
                        if entry_type == "command":
                            if product_search in entry_product or any(product_search in p for p in entry_products):
                                commands.append(cmd_name)
                                break
        result["commands"] = sorted(set(commands))[:20]
        result["command_count"] = len(set(commands))

        # 설정 파일 검색
        configs_dir = self.summaries_dir / "configs"
        config_file = configs_dir / f"{product_key}.md"
        if config_file.exists():
            try:
                content = config_file.read_text(encoding="utf-8")
                # 설정 항목 추출 (테이블 행 수)
                config_lines = re.findall(r"^\| `([^`]+)`", content, re.MULTILINE)
                result["configs"] = config_lines[:20]
                result["config_count"] = len(config_lines)
            except Exception as e:
                logger.debug(f"설정 파일 읽기 실패: {e}")

        return result if (result["api_count"] > 0 or result["command_count"] > 0) else None

    async def get_product_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 제품 컨텍스트 생성

        "OpenFrame Base에 대해서 알려줘" 같은 제품 관련 질문 감지
        """
        # 제품명 패턴 감지
        product_patterns = [
            (r"(?:openframe\s+)?(base)(?:\s*제품)?", "OpenFrame Base"),
            (r"(?:openframe\s+)?(batch)(?:\s*제품)?", "OpenFrame Batch"),
            (r"(?:openframe\s+)?(common)(?:\s*제품)?", "OpenFrame Common"),
            (r"(?:openframe\s+)?(tacf)(?:\s*제품)?", "OpenFrame TACF"),
            (r"(?:openframe\s+)?(osc)(?:\s*제품)?", "OpenFrame OSC"),
            (r"(?:openframe\s+)?(osi)(?:\s*제품)?", "OpenFrame OSI"),
            (r"(?:openframe\s+)?(tjes)(?:\s*제품)?", "OpenFrame TJES"),
            (r"(?:openframe\s+)?(hidb)(?:\s*제품)?", "OpenFrame HiDB"),
            (r"(?:^|[^a-zA-Z])(tmax)(?:$|[^a-zA-Z])", "Tmax"),
            (r"(?:^|[^a-zA-Z])(tibero)(?:$|[^a-zA-Z])", "Tibero"),
        ]

        # 제품 요약 요청 키워드
        summary_keywords = ["요약", "알려", "설명", "뭐야", "무엇", "소개", "개요", "about", "summary"]
        query_lower = query.lower()

        # 요약 요청인지 확인
        is_summary_request = any(kw in query_lower for kw in summary_keywords)
        if not is_summary_request:
            return None

        # 제품명 찾기
        detected_product = None
        for pattern, product_name in product_patterns:
            if re.search(pattern, query_lower, re.IGNORECASE):
                detected_product = product_name
                break

        if not detected_product:
            return None

        # 제품 정보 검색
        result = await self.search_product(detected_product)
        if not result:
            return None

        # 컨텍스트 생성
        ctx_parts = [f"## {result['product']} 제품 요약\n"]

        # 통계
        ctx_parts.append(f"**구성 요소:**")
        ctx_parts.append(f"- API 함수: {result['api_count']}개")
        ctx_parts.append(f"- 명령어: {result['command_count']}개")
        if result['config_count'] > 0:
            ctx_parts.append(f"- 설정 파라미터: {result['config_count']}개")

        # 주요 API 목록
        if result['apis']:
            ctx_parts.append(f"\n**주요 API 함수 (상위 {len(result['apis'])}개):**")
            for api in result['apis'][:10]:
                ctx_parts.append(f"- `{api}()`")
            if len(result['apis']) > 10:
                ctx_parts.append(f"- ... 외 {len(result['apis']) - 10}개")

        # 주요 명령어 목록
        if result['commands']:
            ctx_parts.append(f"\n**주요 명령어 (상위 {len(result['commands'])}개):**")
            for cmd in result['commands'][:10]:
                ctx_parts.append(f"- `{cmd}`")
            if len(result['commands']) > 10:
                ctx_parts.append(f"- ... 외 {len(result['commands']) - 10}개")

        # 주요 설정
        if result['configs']:
            ctx_parts.append(f"\n**주요 설정 파라미터:**")
            for cfg in result['configs'][:5]:
                ctx_parts.append(f"- `{cfg}`")
            if len(result['configs']) > 5:
                ctx_parts.append(f"- ... 외 {result['config_count'] - 5}개")

        return "\n".join(ctx_parts)


# 싱글톤 인스턴스
_summary_service: Optional[SummarySearchService] = None


def get_summary_search_service() -> SummarySearchService:
    """SummarySearchService 싱글톤 반환"""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummarySearchService()
    return _summary_service
