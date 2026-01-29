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

# MetadataConfigService lazy import to avoid circular dependencies
_metadata_config_service = None

async def _get_metadata_config_service():
    """Lazy load MetadataConfigService."""
    global _metadata_config_service
    if _metadata_config_service is None:
        try:
            from .metadata_config_service import get_metadata_config_service
            _metadata_config_service = await get_metadata_config_service()
            logger.info("MetadataConfigService loaded for SummarySearchService")
        except Exception as e:
            logger.warning(f"Failed to load MetadataConfigService: {e}")
    return _metadata_config_service


class SummarySearchService:
    """매뉴얼 요약본 검색 서비스

    에러 코드, 용어 등을 요약본에서 빠르게 검색하여
    RAG 쿼리를 보강하는 컨텍스트를 제공합니다.
    """

    def __init__(self, summaries_dir: Optional[Path] = None):
        if summaries_dir:
            self.summaries_dir = summaries_dir
        else:
            # /opt/kms 경로 우선, 로컬 경로 폴백
            opt_path = Path("/opt/kms/uploads/summaries")
            local_path = Path("uploads/summaries")
            # 실제 데이터(error-codes 등)가 있는 경로를 선택
            if opt_path.exists() and (opt_path / "error-codes").exists():
                self.summaries_dir = opt_path
            elif local_path.exists():
                self.summaries_dir = local_path
            else:
                self.summaries_dir = opt_path
        self.error_codes_dir = self.summaries_dir / "error-codes"
        self.glossary_dir = self.summaries_dir / "glossary"
        self.commands_dir = self.summaries_dir / "commands"
        self.configs_dir = self.summaries_dir / "configs"
        self.terms_dir = self.summaries_dir / "terms"
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

        # Try to get error file from MetadataConfigService first
        target_file = None
        try:
            metadata_service = await _get_metadata_config_service()
            if metadata_service:
                file_path = await metadata_service.get_error_file(code_int)
                if file_path:
                    target_file = self.error_codes_dir / file_path
                    logger.debug(f"Error file from metadata: {file_path}")
        except Exception as e:
            logger.debug(f"Metadata error lookup failed: {e}")

        # Fallback to hardcoded module_ranges if metadata lookup failed
        if not target_file:
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
        """모든 명령어 파일에서 검색 (폴백)

        단일 문자 파일(D.md 등)뿐만 아니라 OpenFrame_*.md 파일도 검색
        """
        if not self.commands_dir.exists():
            return None

        for file_path in self.commands_dir.glob("*.md"):
            if file_path.name == "index.md":
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                # 명령어 섹션 전체 추출
                pattern = rf"## {re.escape(cmd)}\n(.*?)(?=\n## [a-zA-Z]|\Z)"
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    details = match.group(1).strip()
                    return self._parse_command_section(cmd, details, file_path.name)
            except Exception:
                pass

        return None

    def _parse_command_section(self, cmd: str, details: str, source_file: str) -> Dict[str, Any]:
        """명령어 섹션 텍스트를 파싱하여 구조화된 딕셔너리 반환"""
        # 구조화된 형식 (**설명**: ...) 우선 시도
        desc_match = re.search(r"\*\*설명\*\*:\s*(.+?)(?:\n-|\n\*\*|$)", details, re.DOTALL)
        syntax_match = re.search(r"\*\*구문\*\*:\s*`(.+?)`", details, re.DOTALL)
        ref_match = re.search(r"\*\*참조\*\*:\s*(.+?)(?:\n|$)", details)
        source_match = re.search(r"소스:\s*(.+?)(?:\n|$)", details)

        description = ""
        if desc_match:
            description = ' '.join(desc_match.group(1).strip().split())
        else:
            # 비구조화 형식: ## 명령어 다음 첫 줄이 설명
            lines = [l.strip() for l in details.split("\n") if l.strip() and not l.strip().startswith("-") and not l.strip().startswith("```") and not l.strip().startswith("**")]
            if lines:
                description = lines[0][:300]

        syntax = ""
        if syntax_match:
            syntax = syntax_match.group(1).strip()
        else:
            # ```...``` 블록에서 구문 추출
            code_match = re.search(r"```\n?(.*?)```", details, re.DOTALL)
            if code_match:
                syntax = code_match.group(1).strip()[:200]

        reference = ""
        if ref_match:
            reference = ref_match.group(1).strip()
        elif source_match:
            reference = source_match.group(1).strip()

        # 지원 제품 추출
        products_match = re.search(r"\*\*지원 제품\*\*:\s*(.+?)(?:\n|$)", details)
        products = []
        if products_match:
            products = [p.strip() for p in products_match.group(1).split(",")]

        return {
            "command": cmd.lower(),
            "products": products,
            "multi_product": len(products) > 1,
            "description": description,
            "syntax": syntax,
            "reference": reference,
            "source_file": source_file,
        }

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
        """Agent용 용어 컨텍스트 생성

        특정 VSAM 타입(ESDS, KSDS 등)이 언급되면 일반 'VSAM' 용어는 스킵하여
        혼동을 방지합니다.
        """
        # \b가 CJK 문자와 함께 동작하지 않으므로 커스텀 패턴 사용
        terms = re.findall(r"(?:^|[^A-Za-z])([A-Z]{2,}[A-Z0-9]*)(?=[^A-Za-z]|$)", query)
        if not terms:
            return None

        # VSAM 서브타입이 명시되면 일반 'VSAM' 용어는 스킵 (혼동 방지)
        vsam_subtypes = {"ESDS", "KSDS", "RRDS", "LDS"}
        has_specific_vsam_type = any(t in vsam_subtypes for t in terms)

        # 스킵할 일반 용어들 (서브타입이 명시된 경우)
        generic_parent_terms = {"VSAM"} if has_specific_vsam_type else set()

        contexts = []
        seen = set()
        for term in terms[:3]:
            if term in seen:
                continue
            seen.add(term)

            # 일반 부모 용어 스킵
            if term in generic_parent_terms:
                continue

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
        # 명령어 패턴 감지
        cmd_patterns = [
            r"\b([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b",
            r"\b(tjes[a-z0-9]+|osc[a-z0-9]+|tac[a-z0-9]+|ofm[a-z0-9]+|hidb[a-z0-9]+|ndb[a-z0-9]+|vol[a-z0-9]+|cat[a-z0-9]+|hd[a-z0-9]+|dsm[a-z0-9]+)\b",  # OF 계열 명령어 (added hd*, dsm* for HiDB tools)
            r"([a-z][a-z0-9_-]{3,})(?:이|가|을|를|에|의|란|뭐|무엇)",  # 한국어 질문 패턴
            r"([a-z][a-z0-9_-]{3,})(?:コマンド|について|とは|の説明|を説明|標準|フォーマット)",  # 일본어 질문 패턴 (added 標準, フォーマット)
            r"\b(DFS[A-Z0-9]{3,}|IDB[A-Z0-9]{3,}|IDCAMS|IEBGENER|IEBCOPY|DFSORT)\b",  # 대문자 유틸리티/프로그램명
            r"\b([A-Z]{3,}[A-Z0-9]{2,})(?:에|이|가|을|를|란|뭐|무엇|について|とは)",  # 대문자 + CJK 질문 패턴
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

    async def search_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """설정 파라미터 검색

        Args:
            config_name: 설정 파라미터 이름 (예: "ACCOUNT_LOCK_PERIOD", "AIM")

        Returns:
            설정 정보 딕셔너리 또는 None
        """
        if not config_name or not self.configs_dir.exists():
            return None

        # 모든 설정 파일 검색
        for config_file in self.configs_dir.glob("*.md"):
            if config_file.name == "index.md":
                continue

            try:
                content = config_file.read_text(encoding="utf-8")

                # 설정 파라미터 패턴: ## CONFIG_NAME
                pattern = rf"## {re.escape(config_name)}\n(.*?)(?=\n## [A-Z]|\Z)"
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

                if match:
                    details = match.group(1)

                    product_match = re.search(r"\*\*제품\*\*:\s*(.+?)(?:\n|$)", details)
                    desc_match = re.search(r"\*\*설명\*\*:\s*(.+?)(?:\n-|\n\*\*|$)", details, re.DOTALL)
                    ref_match = re.search(r"\*\*참조\*\*:\s*(.+?)(?:\n|$)", details)

                    description = ""
                    if desc_match:
                        description = ' '.join(desc_match.group(1).strip().split())

                    return {
                        "config": config_name.upper(),
                        "product": product_match.group(1).strip() if product_match else "",
                        "description": description[:300],
                        "reference": ref_match.group(1).strip() if ref_match else "",
                        "source_file": config_file.name,
                    }

            except Exception as e:
                logger.debug(f"설정 파일 파싱 실패: {config_file} - {e}")

        return None

    async def get_config_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 설정 파라미터 컨텍스트 생성

        설정 파라미터 패턴 감지 (대문자_대문자 형식)
        """
        # 설정 파라미터 패턴 감지
        config_patterns = [
            r"\b([A-Z][A-Z0-9_]{2,})\b",  # 대문자+숫자+언더스코어 (3자 이상)
        ]

        # 설정 관련 키워드가 있는지 확인
        config_keywords = ["설정", "파라미터", "config", "parameter", "設定", "パラメータ"]
        query_lower = query.lower()
        has_config_keyword = any(kw in query_lower for kw in config_keywords)

        if not has_config_keyword:
            return None

        configs = []
        for pattern in config_patterns:
            matches = re.findall(pattern, query)
            configs.extend(matches)

        if not configs:
            return None

        contexts = []
        seen = set()
        for config in configs[:3]:
            config_upper = config.upper()
            if config_upper in seen:
                continue
            # 너무 일반적인 약어 제외
            if config_upper in {"THE", "AND", "FOR", "NOT", "ARE", "ALL"}:
                continue
            seen.add(config_upper)

            result = await self.search_config(config_upper)
            if result:
                ctx = f"설정 파라미터 {result['config']}"
                if result.get('product'):
                    ctx += f" ({result['product']})"
                if result.get('description'):
                    ctx += f": {result['description'][:200]}"
                if result.get('reference'):
                    ctx += f"\n  참조: {result['reference']}"
                contexts.append(ctx)

        return "\n\n".join(contexts) if contexts else None

    async def search_term(self, term_name: str) -> Optional[Dict[str, Any]]:
        """도메인 용어 검색 (terms/ 디렉토리)

        glossary와 다른 형식의 용어 정의를 검색합니다.
        terms/는 OpenFrame_*.md 파일에 저장됩니다.

        Args:
            term_name: 용어 이름 (예: "BOOT_STATUS", "ColdBoot", "FLUSH")

        Returns:
            용어 정보 딕셔너리 또는 None
        """
        if not term_name or not self.terms_dir.exists():
            return None

        # 모든 용어 파일 검색
        for term_file in self.terms_dir.glob("*.md"):
            if term_file.name == "index.md":
                continue

            try:
                content = term_file.read_text(encoding="utf-8")

                # 용어 패턴: ## TERM_NAME
                pattern = rf"## {re.escape(term_name)}\n(.*?)(?=\n## |\Z)"
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

                if match:
                    details = match.group(1).strip()

                    # 설명은 첫 줄 (- 소스: 전까지)
                    desc_lines = []
                    source = ""
                    for line in details.split("\n"):
                        line = line.strip()
                        if line.startswith("- 소스:"):
                            source = line.replace("- 소스:", "").strip()
                            break
                        elif line and not line.startswith("-"):
                            desc_lines.append(line)

                    description = " ".join(desc_lines)

                    return {
                        "term": term_name,
                        "description": description[:300],
                        "reference": source,
                        "source_file": term_file.name,
                    }

            except Exception as e:
                logger.debug(f"용어 파일 파싱 실패: {term_file} - {e}")

        return None

    async def get_domain_term_context_for_agent(self, query: str) -> Optional[str]:
        """Agent용 도메인 용어 컨텍스트 생성 (terms/ 디렉토리)

        glossary와 별도로 OpenFrame 도메인 용어 검색
        """
        # 용어 패턴 감지 (CamelCase 또는 대문자_언더스코어)
        # \b가 CJK 문자와 함께 동작하지 않으므로 boundary 제거
        term_patterns = [
            r"([A-Z][a-z]+[A-Z][a-zA-Z]*)",  # CamelCase (e.g., ColdBoot, WarmBoot)
            r"(?:^|[^A-Za-z])([A-Z][A-Z0-9_]+)(?=[^A-Za-z]|$)",  # 대문자_언더스코어 (e.g., BOOT_STATUS)
        ]

        terms = []
        for pattern in term_patterns:
            matches = re.findall(pattern, query)
            terms.extend(matches)

        if not terms:
            return None

        contexts = []
        seen = set()
        for term in terms[:3]:
            if term in seen:
                continue
            # 너무 일반적인 단어 제외
            if term.upper() in {"THE", "AND", "FOR", "NOT", "ARE", "ALL", "WITH", "THIS", "THAT"}:
                continue
            seen.add(term)

            result = await self.search_term(term)
            if result:
                ctx = f"용어 {result['term']}: {result['description'][:150]}"
                if result.get('reference'):
                    ctx += f" (출처: {result['reference']})"
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

        # Try to get product mapping from MetadataConfigService first
        product_key = None
        try:
            metadata_service = await _get_metadata_config_service()
            if metadata_service:
                # Extract keyword from product name
                keywords_to_try = [
                    product_lower.replace("openframe ", "").strip().upper(),
                    product_name.upper(),
                ]
                for kw in keywords_to_try:
                    doc_pattern = await metadata_service.get_document_pattern(kw)
                    if doc_pattern:
                        product_key = f"OpenFrame_{doc_pattern}"
                        logger.debug(f"Product mapping from metadata: {kw} -> {product_key}")
                        break
        except Exception as e:
            logger.debug(f"Metadata product lookup failed: {e}")

        # Fallback to hardcoded product_map if metadata lookup failed
        if not product_key:
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

    async def extract_page_references(self, content: str) -> List[Dict[str, Any]]:
        """Extract PDF page references from summary content.

        Parses patterns like:
        - 출처: OpenFrame_Base.pdf, p.123
        - 참조: OpenFrame_TJES.pdf p.45-50
        - (Source: Manual.pdf, page 100)

        Args:
            content: Summary content text

        Returns:
            List of page reference dicts with pdf_path and page_numbers
        """
        references = []

        # Pattern 1: 출처/참조: filename.pdf, p.123 or p.123-125
        patterns = [
            r'(?:출처|참조|Source|Reference):\s*([^,\n]+\.pdf)[,\s]+p\.?\s*(\d+)(?:-(\d+))?',
            r'([A-Za-z_]+\.pdf)[,\s]+(?:p|page)\.?\s*(\d+)(?:-(\d+))?',
            r'\(([^)]+\.pdf)[,\s]+p\.?\s*(\d+)(?:-(\d+))?\)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                pdf_name = match[0].strip()
                page_start = int(match[1])
                page_end = int(match[2]) if len(match) > 2 and match[2] else page_start

                pages = list(range(page_start, page_end + 1))

                ref = {
                    "pdf_path": pdf_name,
                    "page_numbers": pages,
                    "page_start": page_start,
                    "page_end": page_end,
                }

                # Avoid duplicates
                if ref not in references:
                    references.append(ref)

        return references

    def _extract_cjk_key_terms(self, query: str) -> List[str]:
        """Extract key terms from CJK queries by removing question particles.

        Japanese/Korean queries often contain question particles like:
        - について、とは、を説明、ください、について説明してください
        - 에 대해서, 설명해줘, 알려줘

        We extract the key term (what they're asking about) by removing these.
        """
        # Japanese question particles to remove
        jp_particles = [
            r"について説明してください$",
            r"について教えてください$",
            r"について詳しく$",
            r"について$",
            r"とは何ですか$",
            r"とは$",
            r"を説明してください$",
            r"を教えてください$",
            r"を説明$",
            r"の説明$",
            r"ください$",
            r"ですか$",
            r"ってなに$",
            r"って何$",
        ]

        # Korean question particles to remove
        ko_particles = [
            r"에 대해서 설명해줘$",
            r"에 대해서 알려줘$",
            r"에 대해서$",
            r"에 대해$",
            r"설명해줘$",
            r"알려줘$",
            r"이 뭐야$",
            r"가 뭐야$",
            r"란$",
            r"이란$",
        ]

        all_particles = jp_particles + ko_particles

        # Try removing particles to get key term
        key_terms = []
        clean_query = query.strip()

        for particle in all_particles:
            cleaned = re.sub(particle, "", clean_query, flags=re.IGNORECASE)
            if cleaned != clean_query and len(cleaned) >= 2:
                key_terms.append(cleaned.strip())

        # Also include the original query
        if clean_query not in key_terms:
            key_terms.append(clean_query)

        # Return unique terms, prioritizing shorter (more specific) ones
        unique_terms = list(dict.fromkeys(key_terms))
        return unique_terms[:3]  # Max 3 terms

    async def fulltext_search_summaries(
        self, query: str, max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Full-text search across all summary markdown files.

        Searches for Japanese/CJK and other text that doesn't match
        pattern-based searches (commands, errors, etc.).

        For CJK queries, automatically extracts key terms by removing
        question particles (について、とは、에 대해서, etc.).

        Args:
            query: Search query (can be Japanese, Korean, English)
            max_results: Maximum number of results to return

        Returns:
            List of matching results with file path and context
        """
        results = []
        if not query or len(query) < 2:
            return results

        # Extract key terms for CJK queries
        has_cjk = bool(re.search(r'[\u3000-\u9fff\uac00-\ud7af]', query))
        if has_cjk:
            search_terms = self._extract_cjk_key_terms(query)
            logger.debug(f"Extracted CJK key terms: {search_terms}")
        else:
            search_terms = [query]

        # Search directories (commands has most detailed content)
        search_dirs = [
            self.commands_dir,
            self.terms_dir,
            self.glossary_dir,
            self.configs_dir,
        ]

        # Try each search term
        for search_term in search_terms:
            if len(results) >= max_results:
                break

            # Escape special regex characters in query
            escaped_query = re.escape(search_term)

            for search_dir in search_dirs:
                if not search_dir.exists():
                    continue

                for md_file in search_dir.glob("*.md"):
                    if md_file.name == "index.md":
                        continue

                    try:
                        content = md_file.read_text(encoding="utf-8")

                        # Case-insensitive search
                        if re.search(escaped_query, content, re.IGNORECASE):
                            # Extract context around the match
                            matches = list(re.finditer(
                                escaped_query, content, re.IGNORECASE
                            ))

                            for match in matches[:2]:  # Max 2 contexts per file
                                start = max(0, match.start() - 200)
                                end = min(len(content), match.end() + 500)
                                context = content[start:end]

                                # Find section header (## heading)
                                header_match = re.search(
                                    r"^## (.+?)$",
                                    content[:match.start()],
                                    re.MULTILINE
                                )
                                section = header_match.group(1) if header_match else ""

                                # Find last header before this match
                                all_headers = list(re.finditer(
                                    r"^## (.+?)$", content[:match.start()], re.MULTILINE
                                ))
                                if all_headers:
                                    section = all_headers[-1].group(1)

                                results.append({
                                    "type": "fulltext",
                                    "query": query,
                                    "section": section,
                                    "context": context.strip(),
                                    "score": 0.8,  # High score for exact match
                                    "source_file": md_file.name,
                                    "source_dir": search_dir.name,
                                })

                                if len(results) >= max_results:
                                    return results

                    except Exception as e:
                        logger.debug(f"Error searching {md_file}: {e}")

        return results

    async def comprehensive_search(self, query: str) -> Dict[str, Any]:
        """Unified search across all summary types.

        Used by Summary-First RAG to get all relevant context from summaries.

        Args:
            query: User query

        Returns:
            Dict containing:
            - results: List of matched items with scores
            - confidence: high/medium/low based on scores
            - page_references: PDF page references for loading original content
            - context_string: Formatted string for RAG enrichment
        """
        results = []
        page_references = []

        # 1. Error code search
        error_context = await self.get_error_context_for_agent(query)
        if error_context:
            # Extract error codes from query
            error_codes = re.findall(r"-?\d{4,5}", query)
            for code in error_codes[:3]:
                error_result = await self.search_error_code(code)
                if error_result:
                    results.append({
                        "type": "error_code",
                        "code": error_result.get("code"),
                        "name": error_result.get("name"),
                        "description": error_result.get("description"),
                        "solution": error_result.get("solution"),
                        "score": 1.0,  # Exact match
                        "source_file": error_result.get("source_file"),
                    })
                    # Extract page references
                    refs = await self.extract_page_references(
                        f"출처: {error_result.get('source_file', '')}"
                    )
                    page_references.extend(refs)

        # 2. Command search
        cmd_context = await self.get_command_context_for_agent(query)
        if cmd_context:
            # Extract commands from query (소문자 + 대문자 유틸리티 패턴)
            cmd_patterns = [
                r'\b([a-z][a-z0-9]{2,}(?:init|boot|down|start|stop|run|exec|ctl|mgr|adm|cmd))\b',
                r'\b(tjes[a-z0-9]+|osc[a-z0-9]+|tac[a-z0-9]+|ofm[a-z0-9]+|hidb[a-z0-9]+|ndb[a-z0-9]+|vol[a-z0-9]+|cat[a-z0-9]+|hd[a-z0-9]+|dsm[a-z0-9]+)\b',  # ASCII only (added hd*, dsm* for HiDB tools)
                r'([a-z][a-z0-9_-]{3,})(?:コマンド|について|とは|の説明|を説明|標準|フォーマット)',  # 일본어 질문 패턴 (added 標準, フォーマット)
                r'\b(DFS[A-Z0-9]{3,}|IDB[A-Z0-9]{3,}|IDCAMS|IEBGENER|IEBCOPY|DFSORT)\b',
                r'\b([A-Z]{3,}[A-Z0-9]{2,})(?:에|이|가|을|를|란|뭐|무엇|について|とは)',
            ]
            commands = []
            for pattern in cmd_patterns:
                commands.extend(re.findall(pattern, query, re.IGNORECASE))

            for cmd in list(set(commands))[:3]:
                cmd_result = await self.search_command(cmd.lower())
                if not cmd_result:
                    cmd_result = await self._search_all_commands(cmd.lower())
                if cmd_result:
                    # Multi-product 명령어의 경우 product_info에서 description/syntax 추출
                    description = cmd_result.get("description")
                    syntax = cmd_result.get("syntax")
                    if not description and cmd_result.get("product_info"):
                        first_product = cmd_result["product_info"][0]
                        description = first_product.get("description")
                        syntax = first_product.get("syntax")
                    results.append({
                        "type": "command",
                        "command": cmd_result.get("command"),
                        "description": description,
                        "syntax": syntax,
                        "products": cmd_result.get("products", []),
                        "score": 1.0,
                        "source_file": cmd_result.get("source_file"),
                    })

        # 3. Term/glossary search
        term_context = await self.get_term_context_for_agent(query)
        if term_context:
            # \b가 CJK 문자와 함께 동작하지 않으므로 커스텀 패턴 사용
            terms = re.findall(r"(?:^|[^A-Za-z])([A-Z]{2,}[A-Z0-9]*)(?=[^A-Za-z]|$)", query)
            for term in list(set(terms))[:3]:
                term_result = await self.search_glossary(term)
                if term_result:
                    results.append({
                        "type": "glossary",
                        "term": term_result.get("term"),
                        "full_name": term_result.get("full_name"),
                        "description": term_result.get("description"),
                        "score": 1.0,
                        "source_file": term_result.get("source_file"),
                    })

        # 4. API search
        api_context = await self.get_api_context_for_agent(query)
        if api_context:
            api_patterns = [
                r'(?:^|[^a-z_])([a-z]{2,4}_[a-z_]+)',
            ]
            apis = []
            for pattern in api_patterns:
                apis.extend(re.findall(pattern, query, re.IGNORECASE))

            for api in list(set(apis))[:3]:
                api_result = await self.search_api(api.lower())
                if api_result:
                    results.append({
                        "type": "api",
                        "api": api_result.get("api"),
                        "description": api_result.get("description"),
                        "syntax": api_result.get("syntax"),
                        "product": api_result.get("product"),
                        "score": 1.0,
                        "source_file": api_result.get("source_file"),
                    })

        # 5. Config search (설정 파라미터)
        config_context = await self.get_config_context_for_agent(query)
        if config_context:
            config_patterns = [
                r"\b([A-Z][A-Z0-9_]{2,})\b",
            ]
            configs = []
            for pattern in config_patterns:
                configs.extend(re.findall(pattern, query))

            for config in list(set(configs))[:3]:
                if config.upper() in {"THE", "AND", "FOR", "NOT", "ARE", "ALL"}:
                    continue
                config_result = await self.search_config(config.upper())
                if config_result:
                    results.append({
                        "type": "config",
                        "config": config_result.get("config"),
                        "description": config_result.get("description"),
                        "product": config_result.get("product"),
                        "score": 1.0,
                        "source_file": config_result.get("source_file"),
                    })

        # 6. Domain term search (terms/ 디렉토리 - glossary와 별도)
        domain_term_context = await self.get_domain_term_context_for_agent(query)
        if domain_term_context:
            # \b가 CJK 문자와 함께 동작하지 않으므로 boundary 제거
            term_patterns = [
                r"([A-Z][a-z]+[A-Z][a-zA-Z]*)",  # CamelCase
                r"(?:^|[^A-Za-z])([A-Z][A-Z0-9_]+)(?=[^A-Za-z]|$)",  # UPPER_CASE
            ]
            domain_terms = []
            for pattern in term_patterns:
                domain_terms.extend(re.findall(pattern, query))

            for term in list(set(domain_terms))[:3]:
                if term.upper() in {"THE", "AND", "FOR", "NOT", "ARE", "ALL", "WITH", "THIS", "THAT"}:
                    continue
                term_result = await self.search_term(term)
                if term_result:
                    results.append({
                        "type": "term",
                        "term": term_result.get("term"),
                        "description": term_result.get("description"),
                        "reference": term_result.get("reference"),
                        "score": 1.0,
                        "source_file": term_result.get("source_file"),
                    })

        # 7. Full-text search for CJK/Japanese queries
        # Always run for CJK queries to find specific content
        # Pattern-based searches might find generic terms but miss specific content
        has_cjk = bool(re.search(r'[\u3000-\u9fff\uac00-\ud7af]', query))

        if has_cjk:
            fulltext_results = await self.fulltext_search_summaries(query, max_results=3)
            for ft_result in fulltext_results:
                results.append({
                    "type": "fulltext",
                    "section": ft_result.get("section", ""),
                    "context": ft_result.get("context", ""),
                    "description": ft_result.get("context", "")[:300],
                    "score": ft_result.get("score", 0.8),
                    "source_file": ft_result.get("source_file", ""),
                    "source_dir": ft_result.get("source_dir", ""),
                })
            if fulltext_results:
                logger.info(f"CJK full-text search found {len(fulltext_results)} results for: {query[:50]}")

        # Fallback: full-text search for non-CJK queries with no pattern matches
        elif not results and len(query) > 5:
            fulltext_results = await self.fulltext_search_summaries(query, max_results=3)
            for ft_result in fulltext_results:
                results.append({
                    "type": "fulltext",
                    "section": ft_result.get("section", ""),
                    "context": ft_result.get("context", ""),
                    "description": ft_result.get("context", "")[:300],
                    "score": ft_result.get("score", 0.8),
                    "source_file": ft_result.get("source_file", ""),
                    "source_dir": ft_result.get("source_dir", ""),
                })
            if fulltext_results:
                logger.info(f"Fallback full-text search found {len(fulltext_results)} results for: {query[:50]}")

        # Determine confidence level
        if results:
            max_score = max(r.get("score", 0) for r in results)
            if max_score >= 0.7:
                confidence = "high"
            elif max_score >= 0.4:
                confidence = "medium"
            else:
                confidence = "low"
        else:
            confidence = "low"

        # Build context string
        context_parts = []
        for r in results[:7]:  # 최대 7개 컨텍스트
            if r["type"] == "error_code":
                ctx = f"[에러 {r.get('code')}: {r.get('name')} - {r.get('description', '')}]"
            elif r["type"] == "command":
                ctx = f"[명령어 {r.get('command')}: {r.get('description', '')}]"
            elif r["type"] == "glossary":
                ctx = f"[{r.get('term')}: {r.get('full_name', '')} - {r.get('description', '')}]"
            elif r["type"] == "api":
                ctx = f"[API {r.get('api')}: {r.get('description', '')}]"
            elif r["type"] == "config":
                ctx = f"[설정 {r.get('config')}: {r.get('description', '')}]"
            elif r["type"] == "term":
                ctx = f"[용어 {r.get('term')}: {r.get('description', '')}]"
            elif r["type"] == "fulltext":
                # Full-text search result - include more context
                section = r.get("section", "")
                context_text = r.get("context", "")[:500]  # Limit context length
                source = r.get("source_file", "")
                ctx = f"[참조: {section} ({source})]\n{context_text}"
            else:
                ctx = f"[{r.get('type')}: {str(r)[:100]}]"
            context_parts.append(ctx)

        return {
            "results": results,
            "confidence": confidence,
            "page_references": page_references,
            "context_string": "\n".join(context_parts) if context_parts else "",
            "total_results": len(results),
        }

    # =========================================================================
    # Structure Search Methods (Two-Stage Retrieval용)
    # =========================================================================

    async def search_structure(
        self, pdf_name: str, section_title: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """PDF 문서의 계층 구조 검색

        Args:
            pdf_name: PDF 파일명 (확장자 포함 또는 미포함)
            section_title: 특정 섹션 제목 (선택사항)

        Returns:
            구조 정보 딕셔너리 또는 None
        """
        structures_dir = self.summaries_dir / "structures"
        if not structures_dir.exists():
            logger.debug("structures 디렉토리가 없습니다")
            return None

        # 파일명 정규화
        base_name = Path(pdf_name).stem

        # 구조 파일 찾기
        structure_file = structures_dir / f"{base_name}_structure.json"
        if not structure_file.exists():
            # 부분 매칭 시도
            for f in structures_dir.glob("*_structure.json"):
                if base_name.lower() in f.stem.lower():
                    structure_file = f
                    break
            else:
                logger.debug(f"구조 파일을 찾을 수 없습니다: {base_name}")
                return None

        try:
            data = json.loads(structure_file.read_text(encoding="utf-8"))

            # 특정 섹션 검색
            if section_title:
                node = self._find_node_in_structure(data.get("hierarchy", []), section_title)
                if node:
                    return {
                        "found": True,
                        "document": data.get("title"),
                        "file_name": data.get("file_name"),
                        "node": node,
                        "page_start": node.get("page_start"),
                        "page_end": node.get("page_end"),
                        "summary": node.get("summary"),
                        "keywords": node.get("keywords", []),
                    }
                return None

            # 전체 구조 반환
            return {
                "found": True,
                "title": data.get("title"),
                "file_name": data.get("file_name"),
                "total_pages": data.get("total_pages"),
                "language": data.get("language"),
                "hierarchy": data.get("hierarchy", []),  # Full hierarchy for processing
                "hierarchy_count": self._count_hierarchy_nodes(data.get("hierarchy", [])),
                "images_index": data.get("images_index", []),  # Full image index
                "images_count": len(data.get("images_index", [])),
                "validation": data.get("validation", {}),
                "top_level_sections": [
                    {
                        "title": node.get("title"),
                        "page_start": node.get("page_start"),
                        "page_end": node.get("page_end"),
                        "type": node.get("node_type"),
                    }
                    for node in data.get("hierarchy", [])
                ],
            }

        except Exception as e:
            logger.warning(f"구조 파일 파싱 실패: {structure_file} - {e}")
            return None

    def _find_node_in_structure(
        self, hierarchy: List[Dict], title: str, exact: bool = False
    ) -> Optional[Dict]:
        """계층 구조에서 노드 검색 (재귀적)"""
        for node in hierarchy:
            if exact:
                if node.get("title") == title:
                    return node
            else:
                if title.lower() in node.get("title", "").lower():
                    return node

            # 자식 노드 검색
            children = node.get("children", [])
            if children:
                found = self._find_node_in_structure(children, title, exact)
                if found:
                    return found

        return None

    def _count_hierarchy_nodes(self, hierarchy: List[Dict]) -> int:
        """계층 구조의 전체 노드 수 계산"""
        count = 0
        for node in hierarchy:
            count += 1
            count += self._count_hierarchy_nodes(node.get("children", []))
        return count

    async def get_image_references(
        self, pdf_name: str, ref_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """PDF 문서의 이미지/테이블 참조 목록 반환

        Args:
            pdf_name: PDF 파일명
            ref_type: "figure" 또는 "table" (선택사항)

        Returns:
            이미지 참조 목록
        """
        structures_dir = self.summaries_dir / "structures"
        if not structures_dir.exists():
            return []

        # 파일명 정규화
        base_name = Path(pdf_name).stem

        # 이미지 인덱스 파일 찾기
        images_file = structures_dir / f"{base_name}_images.json"
        if not images_file.exists():
            # 부분 매칭 시도
            for f in structures_dir.glob("*_images.json"):
                if base_name.lower() in f.stem.lower():
                    images_file = f
                    break
            else:
                return []

        try:
            data = json.loads(images_file.read_text(encoding="utf-8"))

            if ref_type == "figure":
                return data.get("figures", [])
            elif ref_type == "table":
                return data.get("tables", [])
            else:
                # 모든 이미지 반환
                return data.get("figures", []) + data.get("tables", [])

        except Exception as e:
            logger.warning(f"이미지 인덱스 파싱 실패: {images_file} - {e}")
            return []

    async def get_structure_for_pages(
        self, pdf_name: str, start_page: int, end_page: int
    ) -> Optional[Dict[str, Any]]:
        """특정 페이지 범위에 해당하는 구조 정보 반환

        Args:
            pdf_name: PDF 파일명
            start_page: 시작 페이지
            end_page: 종료 페이지

        Returns:
            해당 범위의 섹션 정보
        """
        structures_dir = self.summaries_dir / "structures"
        if not structures_dir.exists():
            return None

        base_name = Path(pdf_name).stem
        structure_file = structures_dir / f"{base_name}_structure.json"

        if not structure_file.exists():
            # 부분 매칭 시도
            for f in structures_dir.glob("*_structure.json"):
                if base_name.lower() in f.stem.lower():
                    structure_file = f
                    break
            else:
                return None

        try:
            data = json.loads(structure_file.read_text(encoding="utf-8"))

            # 해당 페이지 범위와 겹치는 노드 찾기
            matching_nodes = []

            def find_overlapping(hierarchy: List[Dict]):
                for node in hierarchy:
                    node_start = node.get("page_start", 0)
                    node_end = node.get("page_end", 0)

                    # 범위 겹침 확인
                    if not (node_end < start_page or node_start > end_page):
                        matching_nodes.append({
                            "id": node.get("id"),
                            "title": node.get("title"),
                            "level": node.get("level"),
                            "type": node.get("node_type"),
                            "page_start": node_start,
                            "page_end": node_end,
                            "summary": node.get("summary"),
                            "keywords": node.get("keywords", []),
                        })

                    # 자식 노드도 확인
                    find_overlapping(node.get("children", []))

            find_overlapping(data.get("hierarchy", []))

            if matching_nodes:
                return {
                    "document": data.get("title"),
                    "file_name": data.get("file_name"),
                    "page_range": f"{start_page}-{end_page}",
                    "matching_sections": matching_nodes,
                    "section_count": len(matching_nodes),
                }

            return None

        except Exception as e:
            logger.warning(f"페이지 범위 검색 실패: {e}")
            return None

    async def list_available_structures(self) -> List[Dict[str, Any]]:
        """사용 가능한 구조 파일 목록 반환"""
        structures_dir = self.summaries_dir / "structures"
        if not structures_dir.exists():
            return []

        structures = []

        # 인덱스 파일 확인
        index_file = structures_dir / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                return data.get("documents", [])
            except Exception:
                pass

        # 개별 파일 스캔
        for f in structures_dir.glob("*_structure.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                structures.append({
                    "file_name": data.get("file_name"),
                    "title": data.get("title"),
                    "pages": data.get("total_pages"),
                    "nodes": self._count_hierarchy_nodes(data.get("hierarchy", [])),
                    "valid": data.get("validation", {}).get("valid", False),
                })
            except Exception:
                continue

        return structures


# 싱글톤 인스턴스
_summary_service: Optional[SummarySearchService] = None


def get_summary_search_service() -> SummarySearchService:
    """SummarySearchService 싱글톤 반환"""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummarySearchService()
    return _summary_service
