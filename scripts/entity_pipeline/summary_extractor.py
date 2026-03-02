"""
Summary Extractor - uploads/summaries/ からEntity辞書を構築

5カテゴリのMarkdownファイルをパースし、Entity名→EntityInfo辞書を返す:
  - commands/*.md   → COMMAND
  - error-codes/*.md → ERROR_CODE
  - configs/*.md    → CONFIG
  - glossary/*.md   → ACRONYM / CONCEPT
  - concepts/*.md   → CONCEPT
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class EntityInfo:
    """Summary由来のEntity情報"""
    name: str
    entity_type: str        # EntityType enum value string
    confidence: float
    aliases: List[str] = field(default_factory=list)
    source_file: str = ""


class SummaryExtractor:
    """Summary Markdown → Entity辞書変換"""

    def __init__(self, summaries_dir: str = "uploads/summaries"):
        self.summaries_dir = Path(summaries_dir)
        self.entity_dict: Dict[str, EntityInfo] = {}

    def load_all(self) -> Dict[str, EntityInfo]:
        """全Summaryカテゴリをロードしてentity辞書を返す"""
        self._load_commands()
        self._load_error_codes()
        self._load_configs()
        self._load_glossary()
        self._load_concepts()
        return self.entity_dict

    def _load_commands(self):
        """commands/*.md → COMMAND entities"""
        cmd_dir = self.summaries_dir / "commands"
        if not cmd_dir.exists():
            return
        for md_file in sorted(cmd_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # ## command_name パターン
            for match in re.finditer(r'^## (\S+)', text, re.MULTILINE):
                name = match.group(1).strip()
                if len(name) < 2 or name.startswith('#') or name.startswith('-'):
                    continue
                key = name.lower()
                if key not in self.entity_dict:
                    self.entity_dict[key] = EntityInfo(
                        name=name,
                        entity_type="command",
                        confidence=0.95,
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )

    def _load_error_codes(self):
        """error-codes/*.md → ERROR_CODE entities"""
        ec_dir = self.summaries_dir / "error-codes"
        if not ec_dir.exists():
            return
        for md_file in sorted(ec_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # ### ERROR_NAME (-XXXX) パターン
            for match in re.finditer(
                r'^### (\S+)\s+\((-\d{4,5})\)', text, re.MULTILINE
            ):
                err_name = match.group(1).strip()
                err_code = match.group(2).strip()
                key = err_name.lower()
                if key not in self.entity_dict:
                    self.entity_dict[key] = EntityInfo(
                        name=err_name,
                        entity_type="error_code",
                        confidence=0.95,
                        aliases=[err_code],
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )
                # エラー番号自体もエントリ追加
                code_key = err_code
                if code_key not in self.entity_dict:
                    self.entity_dict[code_key] = EntityInfo(
                        name=err_code,
                        entity_type="error_code",
                        confidence=0.95,
                        aliases=[err_name],
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )

    def _load_configs(self):
        """configs/*.md → CONFIG entities"""
        cfg_dir = self.summaries_dir / "configs"
        if not cfg_dir.exists():
            return
        for md_file in sorted(cfg_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # テーブル行: | `param_name` | ... |
            for match in re.finditer(r'\|\s*`([^`]+)`\s*\|', text):
                param = match.group(1).strip()
                if len(param) < 2:
                    continue
                key = param.lower()
                if key not in self.entity_dict:
                    self.entity_dict[key] = EntityInfo(
                        name=param,
                        entity_type="config",
                        confidence=0.90,
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )

    def _load_glossary(self):
        """glossary/*.md → ACRONYM entities"""
        gls_dir = self.summaries_dir / "glossary"
        if not gls_dir.exists():
            return
        for md_file in sorted(gls_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # ## TERM_NAME パターン
            # 정식명칭 (正式名称) をalias化
            blocks = re.split(r'^## ', text, flags=re.MULTILINE)
            for block in blocks[1:]:  # skip header
                lines = block.strip().split('\n')
                if not lines:
                    continue
                term_name = lines[0].strip()
                if len(term_name) < 2:
                    continue
                # 정식명칭 (alias)
                aliases = []
                for line in lines[1:]:
                    m = re.match(r'-\s*\*\*정식명칭\*\*:\s*(.+)', line)
                    if m:
                        full_name = m.group(1).strip()
                        if full_name:
                            aliases.append(full_name)
                        break

                key = term_name.lower()
                if key not in self.entity_dict:
                    # 2文字以上の大文字英字 → ACRONYM、それ以外 → CONCEPT
                    if re.match(r'^[A-Z][A-Z0-9_/.-]+$', term_name) and len(term_name) <= 20:
                        etype = "concept"  # EntityType enum: ACRONYM未定義 → conceptで統一
                    else:
                        etype = "concept"
                    self.entity_dict[key] = EntityInfo(
                        name=term_name,
                        entity_type=etype,
                        confidence=0.95,
                        aliases=aliases,
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )

    def _load_concepts(self):
        """concepts/*.md → CONCEPT entities"""
        con_dir = self.summaries_dir / "concepts"
        if not con_dir.exists():
            return
        for md_file in sorted(con_dir.glob("*.md")):
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # ## concept_name パターン
            for match in re.finditer(r'^## (.+)$', text, re.MULTILINE):
                name = match.group(1).strip()
                if len(name) < 2 or name.startswith('#'):
                    continue
                key = name.lower()
                if key not in self.entity_dict:
                    self.entity_dict[key] = EntityInfo(
                        name=name,
                        entity_type="concept",
                        confidence=0.90,
                        source_file=str(md_file.relative_to(self.summaries_dir)),
                    )

    def get_stats(self) -> Dict[str, int]:
        """辞書統計を返す"""
        type_counts: Dict[str, int] = {}
        for info in self.entity_dict.values():
            type_counts[info.entity_type] = type_counts.get(info.entity_type, 0) + 1
        return {
            "total": len(self.entity_dict),
            "by_type": type_counts,
        }
