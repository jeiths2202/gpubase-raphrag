"""
JEUS 매뉴얼을 일본어에서 한국어로 교체하는 스크립트
일본어 JEUS PDF는 폰트 인코딩 문제(MS-PGothic)로 텍스트 추출이 불가능하여
한국어 버전으로 대체합니다.
"""
import json
from pathlib import Path
import pymupdf
import re

def get_korean_jeus_mapping():
    """한국어 JEUS 매뉴얼 파일명 매핑"""
    kr_dir = Path("uploads/manuals/JEUS_8.5_v2.1.1_KR")
    kr_files = list(kr_dir.glob("*.pdf"))

    # 파일명에서 가이드 타입 추출
    mapping = {}
    for f in kr_files:
        name = f.name.lower()
        # 가이드 타입 키워드 추출
        if "application" in name and "deployment" in name:
            mapping["application_deployment"] = f
        elif "application" in name and "client" in name:
            mapping["application_client"] = f
        elif "concurrency" in name:
            mapping["concurrency"] = f
        elif "ejb" in name:
            mapping["ejb"] = f
        elif "introduction" in name:
            mapping["introduction"] = f
        elif "jbatch" in name:
            mapping["jbatch"] = f
        elif "jca" in name:
            mapping["jca"] = f
        elif "jmx" in name:
            mapping["jmx"] = f
        elif "jpa" in name:
            mapping["jpa"] = f
        elif "mq" in name:
            mapping["mq"] = f
        elif "node" in name and "manager" in name:
            mapping["node_manager"] = f
        elif "osgi" in name:
            mapping["osgi"] = f
        elif "reference" in name:
            mapping["reference"] = f
        elif "release" in name:
            mapping["release"] = f
        elif "scheduler" in name:
            mapping["scheduler"] = f
        elif "security" in name:
            mapping["security"] = f
        elif "server" in name and "guide" in name:
            mapping["server"] = f
        elif "session" in name:
            mapping["session"] = f
        elif "snmp" in name:
            mapping["snmp"] = f
        elif "web-engine" in name or "web_engine" in name or "webengine" in name:
            mapping["web_engine"] = f
        elif "web-service" in name or "web_service" in name or "webservice" in name:
            mapping["web_service"] = f
        elif "webadmin" in name:
            mapping["webadmin"] = f
        elif "domain" in name:
            mapping["domain"] = f
        elif "getting" in name and "started" in name:
            mapping["getting_started"] = f

    return mapping

def analyze_korean_pdf(pdf_path: Path) -> dict:
    """한국어 PDF 분석"""
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)

    # TOC 추출
    toc = doc.get_toc()
    toc_items = []
    for item in toc[:10]:  # 상위 10개만
        level, title, page = item
        toc_items.append({
            "level": level,
            "title": title,
            "page": page
        })

    # 가이드 타입 결정
    name = pdf_path.name.lower()
    if "reference" in name:
        guide_type = "reference"
        strategy_id = "S01_TOOL_REFERENCE"
        strategy_name = "Tool Reference"
    elif "introduction" in name or "getting" in name:
        guide_type = "introduction"
        strategy_id = "S12_INTRO_GUIDE"
        strategy_name = "Introduction Guide"
    elif "release" in name:
        guide_type = "release"
        strategy_id = "S16_RELEASE_NOTE"
        strategy_name = "Release Note"
    elif "security" in name:
        guide_type = "admin"
        strategy_id = "S07_ADMIN_GUIDE"
        strategy_name = "Admin Guide"
    elif "server" in name or "domain" in name or "node" in name:
        guide_type = "admin"
        strategy_id = "S07_ADMIN_GUIDE"
        strategy_name = "Admin Guide"
    elif "ejb" in name or "jca" in name or "jpa" in name or "jmx" in name:
        guide_type = "developer"
        strategy_id = "S10_DEVELOPER_GUIDE"
        strategy_name = "Developer Guide"
    else:
        guide_type = "guide"
        strategy_id = "S13_USER_GUIDE"
        strategy_name = "User Guide"

    doc.close()

    return {
        "file_path": f"manuals/JEUS_8.5_v2.1.1_KR/{pdf_path.name}",
        "file_name": pdf_path.name,
        "product": "JEUS",
        "guide_type": guide_type,
        "total_pages": total_pages,
        "toc_items": len(toc),
        "strategy_id": strategy_id,
        "strategy_name": strategy_name,
        "confidence": 0.9,
        "toc_sample": toc_items,
        "language": "ko"  # 한국어 표시
    }

def update_strategy_analysis():
    """strategy_analysis.json 업데이트"""
    strategy_file = Path("uploads/summaries/strategy_analysis.json")

    # 기존 분석 로드
    with open(strategy_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 일본어 JEUS 매뉴얼 제거하고 한국어로 교체
    new_analyses = []
    jeus_jp_count = 0

    for analysis in data["analyses"]:
        # 일본어 JEUS 매뉴얼 건너뛰기
        if "JEUS_8_v2.1.1_JP" in analysis.get("file_path", ""):
            jeus_jp_count += 1
            continue
        new_analyses.append(analysis)

    print(f"Removed {jeus_jp_count} Japanese JEUS manuals")

    # Add Korean JEUS manuals
    kr_dir = Path("uploads/manuals/JEUS_8.5_v2.1.1_KR")
    kr_pdfs = list(kr_dir.glob("*.pdf"))

    for pdf_path in kr_pdfs:
        print(f"Analyzing: {pdf_path.name}")
        analysis = analyze_korean_pdf(pdf_path)
        new_analyses.append(analysis)

    print(f"Added {len(kr_pdfs)} Korean JEUS manuals")

    # Update metadata
    data["analyses"] = new_analyses
    data["metadata"]["total_files"] = len(new_analyses)
    data["metadata"]["analyzed_files"] = len(new_analyses)
    data["metadata"]["note"] = "JEUS manuals replaced with Korean version due to Japanese font encoding issues"

    # Recalculate summaries
    product_summary = {}
    strategy_summary = {}

    for analysis in new_analyses:
        product = analysis.get("product", "Unknown")
        strategy = analysis.get("strategy_id", "Unknown")

        product_summary[product] = product_summary.get(product, 0) + 1
        strategy_summary[strategy] = strategy_summary.get(strategy, 0) + 1

    data["product_summary"] = dict(sorted(product_summary.items(), key=lambda x: -x[1]))
    data["strategy_summary"] = dict(sorted(strategy_summary.items(), key=lambda x: -x[1]))

    # Save
    with open(strategy_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdate completed!")
    print(f"Total manuals: {len(new_analyses)}")
    print(f"JEUS (Korean): {len(kr_pdfs)}")

    return data

if __name__ == "__main__":
    update_strategy_analysis()
