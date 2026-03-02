"""
TOC-based 100% Coverage Dataset Pipeline

Extracts every TOC entry from every PDF across all products,
generates SFT training data for each, then creates DPO at 10% of SFT.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Product directory → product_id mapping ────────────────────────

DIRECTORY_TO_PRODUCT: Dict[str, str] = {
    "MVS_Openframe 7.1_v3.1.3_JP": "openframe_mvs",
    "MSP_Openframe 7.3_v2.1.1_JP": "openframe_msp",
    "VOS3_Openframe 2.0 _v2.1.1 _JP": "openframe_vos3",
    "XSP_Openframe 7.3_v3.2.1_JP": "openframe_xsp",
    "Tibero 7 FixSet01 Manual Set v2.1.1_jp": "tibero7",
    "Tmax_6.0_v2.1.1_JP": "tmax",
    "JEUS_8_v2.1.1_JP": "jeus_jp",
    "JEUS_8.5_v2.1.1_KR": "jeus_kr",
    "WebtoB_5Fix2_v2.1.3_JP": "webtob",
    "OFAsm_4_v3.1.2_JP": "ofasm",
    "OFCOBOL_4_v3.1.2_JP": "ofcobol",
    "OFGW_7_v2.1.3_JP": "ofgw",
    "OFManager_7.2_v3.1.2_JP": "ofmanager",
    "OFMiner_7Fix1_v2.1.5_JP": "ofminer",
    "OFPli_3_v2.1.2_JP": "ofpli",
    "OFStudio_7_v2.1.1_JP": "ofstudio",
    "ProSort_2SP3_v2.1.3_JP": "prosort",
    "ProSync_FS01_JP": "prosync",
    "ProTrieve_v2_1_JP": "protrieve",
}

PRODUCT_DISPLAY_NAMES: Dict[str, str] = {
    "openframe_mvs": "OpenFrame MVS 7.1",
    "openframe_msp": "OpenFrame MSP 7.3",
    "openframe_vos3": "OpenFrame VOS3 2.0",
    "openframe_xsp": "OpenFrame XSP 7.3",
    "tibero7": "Tibero 7",
    "tmax": "Tmax 6.0",
    "jeus_jp": "JEUS 8 (JP)",
    "jeus_kr": "JEUS 8.5 (KR)",
    "webtob": "WebtoB 5",
    "ofasm": "OpenFrame ASM 4",
    "ofcobol": "OFCOBOL 4",
    "ofgw": "OFGW 7",
    "ofmanager": "OFManager 7.2",
    "ofminer": "OFMiner 7",
    "ofpli": "OFPli 3",
    "ofstudio": "OFStudio 7",
    "prosort": "ProSort 2",
    "prosync": "ProSync",
    "protrieve": "ProTrieve",
}

# ── Language detection ────────────────────────────────────────────

_KO_RE = re.compile(r"[\uAC00-\uD7AF]")
_JA_RE = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")


def detect_language(text: str) -> str:
    ko = len(_KO_RE.findall(text[:500]))
    ja = len(_JA_RE.findall(text[:500]))
    if ko > ja and ko > 10:
        return "ko"
    elif ja > 0:
        return "ja"
    return "en"


# ── Data models ───────────────────────────────────────────────────


@dataclass
class TOCEntry:
    """A single TOC entry from a PDF."""
    product: str
    pdf_name: str
    pdf_path: str
    toc_level: int
    title: str
    page: int
    content: str
    language: str
    manual_title: str  # top-level title of the PDF manual

    @property
    def section_id(self) -> str:
        return f"{self.product}::{self.pdf_name}::{self.title}"


@dataclass
class SFTRecord:
    messages: List[Dict[str, str]]
    metadata: Dict[str, str]

    def to_jsonl(self) -> str:
        return json.dumps(
            {"messages": self.messages, "metadata": self.metadata},
            ensure_ascii=False,
        )


@dataclass
class DPORecord:
    prompt: str
    chosen: str
    rejected: str
    metadata: Dict[str, str]

    def to_jsonl(self) -> str:
        return json.dumps(
            {
                "prompt": self.prompt,
                "chosen": self.chosen,
                "rejected": self.rejected,
                "metadata": self.metadata,
            },
            ensure_ascii=False,
        )


# ── Question templates ────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "ja": (
        "あなたはTmaxSoft製品の技術エキスパートです。"
        "マニュアルの内容に基づいて正確に回答してください。"
        "マニュアルに記載されていない情報は回答しないでください。"
    ),
    "ko": (
        "당신은 TmaxSoft 제품 기술 전문가입니다. "
        "매뉴얼 내용을 기반으로 정확하게 답변해주세요. "
        "매뉴얼에 없는 정보는 답변하지 마세요."
    ),
    "en": (
        "You are a TmaxSoft product technical expert. "
        "Answer accurately based on the manual content. "
        "Do not provide information not found in the manual."
    ),
}

Q_TEMPLATES = {
    "ja": [
        "{product}の{title}について説明してください。",
        "{product}の{title}とは何ですか？",
        "{title}について教えてください。",
    ],
    "ko": [
        "{product}의 {title}에 대해 설명해주세요.",
        "{product}의 {title}이란 무엇인가요?",
        "{title}에 대해 알려주세요.",
    ],
    "en": [
        "Explain {title} in {product}.",
        "What is {title} in {product}?",
        "Tell me about {title}.",
    ],
}


# ── Phase 1: TOC Extraction ──────────────────────────────────────


def extract_all_toc_entries(manuals_dir: str) -> List[TOCEntry]:
    """Extract every TOC entry from every PDF across all products."""
    entries: List[TOCEntry] = []
    skipped_toc_titles = {"目次", "索引", "index", "table of contents", "contents"}

    for dir_name in sorted(os.listdir(manuals_dir)):
        dir_path = os.path.join(manuals_dir, dir_name)
        if not os.path.isdir(dir_path):
            continue

        product = DIRECTORY_TO_PRODUCT.get(dir_name)
        if not product:
            logger.warning("Unknown product directory: %s", dir_name)
            continue

        pdfs = sorted(
            f for f in os.listdir(dir_path) if f.lower().endswith(".pdf")
        )
        logger.info(
            "  [%s] %d PDFs found in %s", product, len(pdfs), dir_name
        )

        for pdf_name in pdfs:
            pdf_path = os.path.join(dir_path, pdf_name)
            try:
                pdf_entries = _extract_pdf_toc(
                    pdf_path, pdf_name, product, skipped_toc_titles
                )
                entries.extend(pdf_entries)
            except Exception as e:
                logger.error("  Failed to process %s: %s", pdf_name, e)

    logger.info("Total TOC entries extracted: %d", len(entries))
    return entries


def _extract_pdf_toc(
    pdf_path: str,
    pdf_name: str,
    product: str,
    skip_titles: set,
) -> List[TOCEntry]:
    """Extract TOC entries with content from a single PDF."""
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    if not toc:
        doc.close()
        return []

    # Get manual title from first TOC or filename
    manual_title = toc[0][1] if toc else pdf_name.replace(".pdf", "")

    results: List[TOCEntry] = []

    for i, (level, title, start_page) in enumerate(toc):
        title_clean = title.strip()

        # Skip TOC/Index entries
        if title_clean.lower() in skip_titles:
            continue
        # Skip very short titles (single char)
        if len(title_clean) < 2:
            continue

        # Extract content between this entry and next entry at same/higher level
        content = _extract_section_content(doc, toc, i)

        # Skip sections with too little content
        if len(content.strip()) < 30:
            continue

        lang = detect_language(content)

        results.append(
            TOCEntry(
                product=product,
                pdf_name=pdf_name,
                pdf_path=pdf_path,
                toc_level=level,
                title=title_clean,
                page=start_page,
                content=content,
                language=lang,
                manual_title=manual_title,
            )
        )

    doc.close()
    return results


def _extract_section_content(
    doc: fitz.Document, toc: list, idx: int
) -> str:
    """Extract text content for a TOC entry (from its page to next entry)."""
    level, title, start_page = toc[idx]

    # Find end: next entry at same or higher level
    end_page = start_page + 5  # default: max 5 pages per section
    for j in range(idx + 1, len(toc)):
        next_level, _, next_page = toc[j]
        if next_level <= level:
            end_page = next_page
            break
        # Also stop at deeper entries that are far away
        if toc[j][2] > start_page + 10:
            end_page = toc[j][2]
            break

    # Clamp to document bounds
    end_page = min(end_page, len(doc))
    start_page = max(start_page - 1, 0)  # 0-indexed

    text_parts: List[str] = []
    for pg_num in range(start_page, end_page):
        page_text = doc[pg_num].get_text()
        if page_text:
            text_parts.append(page_text)

    full_text = "\n".join(text_parts)

    # Trim to max 3000 chars to keep answers focused
    if len(full_text) > 3000:
        full_text = full_text[:3000]

    return full_text.strip()


# ── Phase 2: SFT Generation ──────────────────────────────────────

# Regex to strip section number prefixes from TOC titles for question generation
# e.g. "1.1. 概要" → "概要", "第4章 WebtoB 5" → "WebtoB 5", "A.3. マップの作成" → "マップの作成"
_SECTION_PREFIX_RE = re.compile(
    r"^(?:"
    r"第\d+章\s*"                  # 第1章, 第4章
    r"|제\d+장\s*"                 # 제1장 (Korean)
    r"|Chapter\s+\d+[.:]*\s*"     # Chapter 1
    r"|付録\s*[A-Z]?[.:]*\s*"     # 付録 A.
    r"|부록\s*[A-Z]?[.:]*\s*"     # 부록 (Korean)
    r"|Appendix\s+[A-Z]?[.:]*\s*" # Appendix A
    r"|\d+(?:\.\d+)*\.?\s+"       # 1.1. or 44.2.6. or 3.
    r"|[A-Z]\.\d+(?:\.\d+)*\.?\s+" # A.1. or D.4.6.
    r")"
)


def _clean_title_for_question(title: str) -> str:
    """Remove section number prefix from TOC title for cleaner questions."""
    cleaned = _SECTION_PREFIX_RE.sub("", title).strip()
    # If stripping removed everything (e.g. title was just "1.1."), keep original
    return cleaned if len(cleaned) >= 2 else title


def generate_sft(entries: List[TOCEntry]) -> List[SFTRecord]:
    """Generate one SFT record per TOC entry."""
    records: List[SFTRecord] = []

    for entry in entries:
        display_name = PRODUCT_DISPLAY_NAMES.get(entry.product, entry.product)
        lang = entry.language
        sys_prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["ja"])

        # Pick a question template
        templates = Q_TEMPLATES.get(lang, Q_TEMPLATES["ja"])
        q_template = templates[len(records) % len(templates)]

        # Clean section number prefix from title for natural questions
        clean_title = _clean_title_for_question(entry.title)
        question = q_template.format(
            product=display_name, title=clean_title
        )

        # Answer = actual content from the PDF
        answer = _clean_answer(entry.content, entry.title)

        if len(answer) < 30:
            continue

        records.append(
            SFTRecord(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                metadata={
                    "product": entry.product,
                    "language": lang,
                    "source_file": entry.pdf_name,
                    "source_page": entry.page,
                    "toc_title": entry.title,
                    "toc_level": entry.toc_level,
                },
            )
        )

    logger.info("SFT records generated: %d", len(records))
    return records


def _clean_answer(content: str, title: str) -> str:
    """Clean extracted content for use as an answer."""
    lines = content.split("\n")
    cleaned: List[str] = []

    for line in lines:
        stripped = line.strip()
        # Skip empty lines at start
        if not cleaned and not stripped:
            continue
        # Skip page number lines
        if re.match(r"^\d+$", stripped):
            continue
        # Skip lines that are just dots/dashes
        if re.match(r"^[.\-=─━]+$", stripped):
            continue
        # Skip copyright/header lines
        if "Copyright" in stripped or "All rights reserved" in stripped:
            continue
        # Skip PDF header/footer page number lines
        if any(pat.match(stripped) for pat in _PAGE_NUMBER_RE):
            continue
        cleaned.append(stripped)

    result = "\n".join(cleaned).strip()

    # Remove trailing incomplete sentences
    if result and result[-1] not in ("。", ".", "다", "요", "\n"):
        last_period = max(
            result.rfind("。"), result.rfind("."), result.rfind("다.")
        )
        if last_period > len(result) * 0.7:
            result = result[: last_period + 1]

    return result


# ── Phase 3: DPO Generation ──────────────────────────────────────

DPO_STRATEGIES = {
    "fact_mutation": 0.40,
    "cross_product": 0.30,
    "over_claiming": 0.30,
}


def generate_dpo(
    sft_records: List[SFTRecord], target_count: int
) -> List[DPORecord]:
    """Generate DPO preference pairs from SFT records."""
    records: List[DPORecord] = []
    seen_prompts: set = set()

    budget = {
        strategy: max(1, int(target_count * ratio))
        for strategy, ratio in DPO_STRATEGIES.items()
    }

    # Group SFT by product for cross-product DPO
    by_product: Dict[str, List[SFTRecord]] = {}
    for r in sft_records:
        by_product.setdefault(r.metadata["product"], []).append(r)

    products = list(by_product.keys())

    # Strategy 1: Fact mutation — alter facts in the answer
    candidates = list(sft_records)
    random.shuffle(candidates)
    for rec in candidates:
        if len(records) >= budget["fact_mutation"]:
            break
        prompt = rec.messages[1]["content"]
        if prompt in seen_prompts:
            continue
        chosen = rec.messages[2]["content"]
        rejected = _mutate_facts(chosen, rec.metadata.get("language", "ja"))
        if rejected and rejected != chosen:
            seen_prompts.add(prompt)
            records.append(
                DPORecord(
                    prompt=prompt,
                    chosen=chosen,
                    rejected=rejected,
                    metadata={
                        "product": rec.metadata["product"],
                        "language": rec.metadata.get("language", "ja"),
                        "strategy": "fact_mutation",
                        "source_file": rec.metadata.get("source_file", ""),
                    },
                )
            )

    # Strategy 2: Cross-product confusion
    random.shuffle(candidates)
    for rec in candidates:
        if len([r for r in records if r.metadata["strategy"] == "cross_product"]) >= budget["cross_product"]:
            break
        prompt = rec.messages[1]["content"]
        if prompt in seen_prompts:
            continue
        chosen = rec.messages[2]["content"]
        other_product = random.choice([p for p in products if p != rec.metadata["product"]] or products)
        other_records = by_product.get(other_product, [])
        if not other_records:
            continue
        other_rec = random.choice(other_records)
        rejected = other_rec.messages[2]["content"]
        if rejected == chosen:
            continue
        seen_prompts.add(prompt)
        records.append(
            DPORecord(
                prompt=prompt,
                chosen=chosen,
                rejected=rejected,
                metadata={
                    "product": rec.metadata["product"],
                    "language": rec.metadata.get("language", "ja"),
                    "strategy": "cross_product",
                    "source_file": rec.metadata.get("source_file", ""),
                },
            )
        )

    # Strategy 3: Over-claiming — add fabricated features
    random.shuffle(candidates)
    for rec in candidates:
        if len([r for r in records if r.metadata["strategy"] == "over_claiming"]) >= budget["over_claiming"]:
            break
        prompt = rec.messages[1]["content"]
        if prompt in seen_prompts:
            continue
        chosen = rec.messages[2]["content"]
        rejected = _add_fabrication(chosen, rec.metadata.get("language", "ja"))
        if rejected and rejected != chosen:
            seen_prompts.add(prompt)
            records.append(
                DPORecord(
                    prompt=prompt,
                    chosen=chosen,
                    rejected=rejected,
                    metadata={
                        "product": rec.metadata["product"],
                        "language": rec.metadata.get("language", "ja"),
                        "strategy": "over_claiming",
                        "source_file": rec.metadata.get("source_file", ""),
                    },
                )
            )

    random.shuffle(records)
    records = records[:target_count]
    logger.info("DPO records generated: %d", len(records))
    return records


_FAKE_FEATURES_JA = [
    "この機能はAI自動最適化をサポートしています。",
    "クラウドネイティブ環境でのリアルタイムスケーリングが可能です。",
    "ブロックチェーンベースの監査証跡が組み込まれています。",
    "量子コンピューティング対応のインターフェースを備えています。",
    "自動障害予測AIエンジンが搭載されています。",
]
_FAKE_FEATURES_KO = [
    "이 기능은 AI 자동 최적화를 지원합니다.",
    "클라우드 네이티브 환경에서의 실시간 스케일링이 가능합니다.",
    "블록체인 기반의 감사 추적이 내장되어 있습니다.",
    "자동 장애 예측 AI 엔진이 탑재되어 있습니다.",
]


def _mutate_facts(text: str, lang: str) -> str:
    """Mutate facts in the text to create a rejected answer."""
    lines = text.split("\n")
    if len(lines) < 2:
        return ""

    # Strategy: shuffle some lines, remove some, swap numbers
    mutated = list(lines)

    # Swap two random content lines
    content_indices = [i for i, l in enumerate(mutated) if len(l.strip()) > 10]
    if len(content_indices) >= 2:
        a, b = random.sample(content_indices, 2)
        mutated[a], mutated[b] = mutated[b], mutated[a]

    # Remove 1-2 lines
    remove_count = min(2, len(content_indices) // 3)
    for _ in range(remove_count):
        if content_indices:
            idx = random.choice(content_indices)
            if idx < len(mutated):
                mutated[idx] = ""
                content_indices.remove(idx)

    result = "\n".join(mutated)
    if result == text:
        # Force mutation: add wrong number
        result = re.sub(r"\d+", lambda m: str(int(m.group()) + random.randint(1, 99)), result, count=1)

    return result


def _add_fabrication(text: str, lang: str) -> str:
    """Add fabricated features to create a rejected answer."""
    if lang == "ko":
        fake = random.choice(_FAKE_FEATURES_KO)
    else:
        fake = random.choice(_FAKE_FEATURES_JA)
    return text + "\n\n" + fake


# ── Phase 5: CPT Corpus Generation ──────────────────────────────

# TOC titles to skip for CPT (noise, not training-worthy content)
_CPT_SKIP_TITLES = {
    "目次", "索引", "index", "table of contents", "contents",
    "はじめに", "改版履歴", "変更履歴", "revision history",
    "著作権", "copyright", "license", "ライセンス",
    "商標", "trademarks", "お問い合わせ", "お問合せ",
    "表記規則", "表記について", "conventions",
    "関連マニュアル", "関連文書", "related documents",
    "付録", "appendix", "내용 목차", "안내서에 대하여",
}

# Content-level boilerplate patterns to detect and skip entire sections
_CPT_BOILERPLATE_RE = re.compile(
    r"(Restricted Rights Legend|All TmaxSoft Software|"
    r"protected by copyright laws|Trademarks\n.*registered trademark|"
    r"사용설명서의 내용과 프로그램은 저작권법|"
    r"등록 상표입니다)",
    re.IGNORECASE,
)

# Regex patterns for lines to strip from CPT text
_CPT_NOISE_RE = [
    re.compile(r"^\d+$"),                       # bare page numbers
    re.compile(r"^[.\-=─━…·•]+$"),              # separator lines
    re.compile(r"^(Copyright|©|All rights reserved)", re.I),
    re.compile(r"^(TmaxSoft|Tmax Data|TIBERO)", re.I),  # header/footer branding
    re.compile(r"^\s*第?\d+章\s*$"),              # bare chapter numbers like "第3章"
    re.compile(r"^\s*Chapter\s+\d+\s*$", re.I),
    re.compile(r"^\f"),                          # form feed characters
    re.compile(r"\.{4,}"),                       # TOC index lines with dots (title .... page)
    re.compile(r"^Restricted Rights Legend", re.I),
    re.compile(r"^Website\s*$", re.I),
    re.compile(r"^(Tel|E-Mail)\s*:", re.I),      # contact info lines
    re.compile(r"^http[s]?://"),                 # bare URLs
]

# PDF header/footer page number patterns (matched separately for clarity)
_PAGE_NUMBER_RE = [
    # "제1장 Title   1" or "第1章 Title   1" — chapter title + trailing page number
    re.compile(r"^(제\d+장|第\d+章)\s+.+\s{2,}\d+$"),
    # "1. Title | 1" — numbered section + pipe + page number
    re.compile(r"^[\d.]+\s+.+\s*\|\s*\d+$"),
    # "6   JEUS Applications & Deployment 안내서" — leading page number + title
    re.compile(r"^\d+\s{2,}\S.+($|ガイド$|안내서$|マニュアル$|리퍼런스$|手引き$)"),
    # "このガイドについて   vii" — title + trailing roman numeral
    re.compile(r"^.+\s{2,}[ivxlc]+$", re.I),
    # "Title   N" — generic title + 2+ spaces + bare page number at end
    re.compile(r"^.{5,}\s{3,}\d{1,4}$"),
]

MIN_CPT_SECTION_CHARS = 50  # skip sections shorter than this


def generate_cpt(entries: List[TOCEntry]) -> str:
    """
    Generate CPT (Continued Pre-Training) corpus from TOC entries.

    Entries are kept in their natural TOC order (product → PDF → page),
    grouped by product. Noise sections (TOC, index, copyright, revision
    history, etc.) are skipped. Each section is separated by <|endoftext|>.
    """
    sections: List[str] = []
    skipped = 0

    # Entries are already in product → PDF → page order from Phase 1
    for entry in entries:
        # Skip noise titles
        title_lower = entry.title.lower().strip()
        if title_lower in _CPT_SKIP_TITLES or any(
            skip in title_lower for skip in _CPT_SKIP_TITLES
        ):
            skipped += 1
            continue

        # Skip sections whose content is mostly boilerplate (copyright, trademark)
        if _CPT_BOILERPLATE_RE.search(entry.content):
            skipped += 1
            continue

        # Clean the content for CPT (plain text, no Q-A framing)
        cleaned = _clean_cpt_text(entry.content)

        if len(cleaned) < MIN_CPT_SECTION_CHARS:
            skipped += 1
            continue

        # Prepend section header for context
        display_name = PRODUCT_DISPLAY_NAMES.get(entry.product, entry.product)
        header = f"# {display_name} — {entry.manual_title} — {entry.title}"
        section = f"{header}\n\n{cleaned}"
        sections.append(section)

    logger.info(
        "CPT sections: %d kept, %d skipped (noise/short)",
        len(sections), skipped,
    )

    # Join with <|endoftext|> separator
    corpus = "\n<|endoftext|>\n".join(sections)
    if corpus:
        corpus += "\n<|endoftext|>\n"

    return corpus


def _clean_cpt_text(content: str) -> str:
    """Clean raw PDF text for CPT corpus — remove noise lines, normalize whitespace."""
    lines = content.split("\n")
    cleaned: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Collapse multiple blank lines into one
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue

        # Check noise patterns
        if any(pat.match(stripped) for pat in _CPT_NOISE_RE):
            continue

        # Check page number header/footer patterns
        if any(pat.match(stripped) for pat in _PAGE_NUMBER_RE):
            continue

        # Skip very short lines that are just artifacts (1-2 chars)
        if len(stripped) <= 2 and not stripped.isalnum():
            continue

        cleaned.append(stripped)

    # Remove leading/trailing blank lines
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    result = "\n".join(cleaned)

    # Remove trailing incomplete sentence (same logic as _clean_answer)
    if result and result[-1] not in ("。", ".", "다", "요", "\n"):
        last_period = max(
            result.rfind("。"), result.rfind("."), result.rfind("다.")
        )
        if last_period > len(result) * 0.7:
            result = result[: last_period + 1]

    return result


# ── Phase 4: Write Output ────────────────────────────────────────


def write_output(
    sft_records: List[SFTRecord],
    dpo_records: List[DPORecord],
    output_dir: str,
    train_ratio: float = 0.8,
    cpt_corpus: Optional[str] = None,
):
    """Write SFT, DPO, and CPT to output files with train/eval split."""
    os.makedirs(output_dir, exist_ok=True)

    # Shuffle before split
    sft_shuffled = list(sft_records)
    random.shuffle(sft_shuffled)

    sft_split = int(len(sft_shuffled) * train_ratio)
    sft_train = sft_shuffled[:sft_split]
    sft_eval = sft_shuffled[sft_split:]

    dpo_shuffled = list(dpo_records)
    random.shuffle(dpo_shuffled)

    dpo_split = int(len(dpo_shuffled) * train_ratio)
    dpo_train = dpo_shuffled[:dpo_split]
    dpo_eval = dpo_shuffled[dpo_split:]

    # Write files
    _write_jsonl(sft_train, os.path.join(output_dir, "sft_train.jsonl"))
    _write_jsonl(sft_eval, os.path.join(output_dir, "sft_eval.jsonl"))
    _write_jsonl(dpo_train, os.path.join(output_dir, "dpo_train.jsonl"))
    _write_jsonl(dpo_eval, os.path.join(output_dir, "dpo_eval.jsonl"))

    # Write CPT corpus
    cpt_size = 0
    cpt_sections = 0
    if cpt_corpus:
        cpt_path = os.path.join(output_dir, "cpt_corpus.txt")
        with open(cpt_path, "w", encoding="utf-8") as f:
            f.write(cpt_corpus)
        cpt_size = len(cpt_corpus)
        cpt_sections = cpt_corpus.count("<|endoftext|>")
        logger.info(
            "  CPT corpus: %s (%.1f MB, %d sections)",
            cpt_path, cpt_size / 1024 / 1024, cpt_sections,
        )

    # Write stats
    stats = {
        "sft_total": len(sft_records),
        "sft_train": len(sft_train),
        "sft_eval": len(sft_eval),
        "dpo_total": len(dpo_records),
        "dpo_train": len(dpo_train),
        "dpo_eval": len(dpo_eval),
        "dpo_ratio": f"{len(dpo_records)/len(sft_records)*100:.1f}%" if sft_records else "0%",
        "products": len(set(r.metadata["product"] for r in sft_records)),
        "cpt_sections": cpt_sections,
        "cpt_size_bytes": cpt_size,
        "sft_by_product": _count_by(sft_records, "product"),
        "sft_by_language": _count_by(sft_records, "language"),
        "dpo_by_strategy": _count_by(dpo_records, "strategy"),
    }

    stats_path = os.path.join(output_dir, "pipeline_stats.json")
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    logger.info("Output written to %s", output_dir)
    logger.info(
        "  SFT: %d (train=%d, eval=%d)",
        len(sft_records), len(sft_train), len(sft_eval),
    )
    logger.info(
        "  DPO: %d (train=%d, eval=%d) = %.1f%% of SFT",
        len(dpo_records), len(dpo_train), len(dpo_eval),
        len(dpo_records) / max(len(sft_records), 1) * 100,
    )
    logger.info("  Stats: %s", stats_path)


def _write_jsonl(records, path: str):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(r.to_jsonl() + "\n")
    logger.info("  Wrote %d records to %s", len(records), path)


def _count_by(records, key: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in records:
        val = r.metadata.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ── Main ──────────────────────────────────────────────────────────


def main():
    manuals_dir = "uploads/manuals"
    output_dir = "dataset_pipeline/output"

    logger.info("=" * 60)
    logger.info("TOC-Based 100%% Coverage Dataset Pipeline")
    logger.info("=" * 60)

    # Phase 1: Extract all TOC entries
    logger.info("\n[Phase 1/5] Extracting TOC entries from all PDFs...")
    entries = extract_all_toc_entries(manuals_dir)

    # Phase 2: Generate SFT (1 record per TOC entry)
    logger.info("\n[Phase 2/5] Generating SFT records...")
    sft_records = generate_sft(entries)

    # Phase 3: Generate DPO (10% of SFT)
    dpo_target = max(1, len(sft_records) // 10)
    logger.info(
        "\n[Phase 3/5] Generating DPO records (target=%d = 10%% of %d)...",
        dpo_target, len(sft_records),
    )
    dpo_records = generate_dpo(sft_records, dpo_target)

    # Phase 4: Generate CPT corpus (TOC order, noise filtered)
    logger.info("\n[Phase 4/5] Generating CPT corpus (TOC order)...")
    cpt_corpus = generate_cpt(entries)

    # Phase 5: Write output
    logger.info("\n[Phase 5/5] Writing output files...")
    write_output(sft_records, dpo_records, output_dir, cpt_corpus=cpt_corpus)

    logger.info("\n" + "=" * 60)
    logger.info("Pipeline complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
