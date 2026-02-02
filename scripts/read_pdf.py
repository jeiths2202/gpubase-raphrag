#!/usr/bin/env python3
"""PDF 텍스트 추출 도구 - OpenCode용"""
import sys
import argparse

def extract_text_from_pdf(pdf_path: str, pages: str = None) -> str:
    """PDF에서 텍스트 추출

    Args:
        pdf_path: PDF 파일 경로
        pages: 페이지 범위 (예: "1-10", "5", "1,3,5-7")

    Returns:
        추출된 텍스트
    """
    try:
        import pdfplumber
    except ImportError:
        try:
            import PyPDF2
            return extract_with_pypdf2(pdf_path, pages)
        except ImportError:
            return "Error: pdfplumber 또는 PyPDF2가 필요합니다. pip install pdfplumber"

    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        page_indices = parse_page_range(pages, total_pages) if pages else range(total_pages)

        for i in page_indices:
            if 0 <= i < total_pages:
                page = pdf.pages[i]
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"=== Page {i+1} ===\n{page_text}")

    return "\n\n".join(text_parts)


def extract_with_pypdf2(pdf_path: str, pages: str = None) -> str:
    """PyPDF2로 텍스트 추출 (fallback)"""
    import PyPDF2

    text_parts = []

    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        total_pages = len(reader.pages)
        page_indices = parse_page_range(pages, total_pages) if pages else range(total_pages)

        for i in page_indices:
            if 0 <= i < total_pages:
                page = reader.pages[i]
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"=== Page {i+1} ===\n{page_text}")

    return "\n\n".join(text_parts)


def parse_page_range(pages_str: str, total: int) -> list:
    """페이지 범위 파싱 (예: "1-10,15,20-25")"""
    indices = []
    for part in pages_str.split(','):
        part = part.strip()
        if '-' in part:
            start, end = part.split('-', 1)
            start = int(start) - 1  # 0-indexed
            end = int(end)  # inclusive
            indices.extend(range(start, min(end, total)))
        else:
            indices.append(int(part) - 1)
    return indices


def search_in_pdf(pdf_path: str, keyword: str) -> str:
    """PDF에서 키워드 검색"""
    try:
        import pdfplumber
    except ImportError:
        return "Error: pdfplumber가 필요합니다."

    results = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text and keyword.lower() in text.lower():
                # 키워드 주변 컨텍스트 추출
                lines = text.split('\n')
                for j, line in enumerate(lines):
                    if keyword.lower() in line.lower():
                        context_start = max(0, j - 2)
                        context_end = min(len(lines), j + 3)
                        context = '\n'.join(lines[context_start:context_end])
                        results.append(f"=== Page {i+1}, Line {j+1} ===\n{context}")

    if not results:
        return f"'{keyword}'를 찾을 수 없습니다."

    return "\n\n".join(results[:20])  # 최대 20개 결과


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF 텍스트 추출 도구")
    parser.add_argument("pdf_path", help="PDF 파일 경로")
    parser.add_argument("--pages", "-p", help="페이지 범위 (예: 1-10, 5, 1,3,5-7)")
    parser.add_argument("--search", "-s", help="키워드 검색")

    args = parser.parse_args()

    if args.search:
        print(search_in_pdf(args.pdf_path, args.search))
    else:
        print(extract_text_from_pdf(args.pdf_path, args.pages))
