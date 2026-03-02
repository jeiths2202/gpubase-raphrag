"""SPOOL 파일 분류 Agent

zip 파일에서 추출된 파일을 OpenFrame TJES SPOOL 데이터셋 유형으로 분류합니다.

분류 전략 (2단계):
  1. 파일명 패턴 매칭 (fast path)
  2. 콘텐츠 패턴 매칭 (fallback)

참조: OF7/OpenFrame7_MVS/batch/include/spool.h
  - SPOOL 데이터셋: INPJCL, JESMSG, SYSMSG, JESJCL, SYSPRINT, SYSOUT
  - 네이밍: <catalog>.<jobname>.<job-id>.<sequence>
"""
import io
import os
import re
import zipfile
from typing import List

from app.api.models.jcl_diagnosis import (
    ClassifiedFile, ClassifiedFiles, SpoolFileType
)


class FileProcessor:
    """zip 해제 + SPOOL 파일 유형 분류"""

    # ─── 파일명 기반 분류 패턴 ─────────────────
    # 참조: OF_Batch_MVS_7.1_TJES-Guide_v3.1.3_jp.pdf 第4章 スプール
    # デフォルト・データセット: INPJCL, SYSMSG, CATPROC, CONVJCL, JESMSG, JESJCL
    # SYSOUT DD: oframe.JOBNAME.JOBID.Dnnnnnn
    FILENAME_PATTERNS = {
        SpoolFileType.JCL: [
            re.compile(r'.*\.(jcl|JCL)$'),
            re.compile(r'.*INPJCL.*', re.IGNORECASE),
            # CONVJCL = プロシージャ展開済みJCL (XX/++/X/ prefix)
            re.compile(r'.*CONVJCL.*', re.IGNORECASE),
        ],
        SpoolFileType.PROC: [
            re.compile(r'.*\.(proc|PROC|prc|PRC)$'),
            # CATPROC = カタログ式プロシージャ内容保存
            re.compile(r'.*CATPROC.*', re.IGNORECASE),
        ],
        SpoolFileType.JESJCL: [
            re.compile(r'.*JESJCL.*', re.IGNORECASE),
        ],
        SpoolFileType.JESMSG: [
            re.compile(r'.*JES(MSG|MSGLG).*', re.IGNORECASE),
        ],
        SpoolFileType.SYSMSG: [
            re.compile(r'.*SYS(MSG|YSMSG).*', re.IGNORECASE),
            re.compile(r'.*JESYSMSG.*', re.IGNORECASE),
        ],
        SpoolFileType.SYSPRINT: [
            re.compile(r'.*SYSPRINT.*', re.IGNORECASE),
        ],
        SpoolFileType.SYSOUT: [
            re.compile(r'.*SYSOUT.*', re.IGNORECASE),
            re.compile(r'.*SPOOL.*', re.IGNORECASE),
        ],
    }

    # ─── 콘텐츠 기반 분류 패턴 (fallback) ──────
    # TJES SPOOL 데이터셋 콘텐츠 패턴
    CONTENT_PATTERNS = {
        SpoolFileType.JCL: re.compile(
            r'^//\w+\s+JOB\s'           # 표준 JCL JOB 카드
            r'|^XX\w*\s+EXEC\s'         # CONVJCL: カタログ式プロシージャ展開
            , re.MULTILINE
        ),
        SpoolFileType.JESMSG: re.compile(
            r'---<\s*JOB\s+INFO\s*>---'  # TJES JESMSG ヘッダ
            r'|JOB\s+NAME\s*:'           # JOB NAME フィールド
            r'|---<STEP\s+INFO>---'      # STEP INFO セクション
            , re.MULTILINE
        ),
        SpoolFileType.SYSMSG: re.compile(
            r'JOBID=JOB\d+'              # SYSMSG先頭行: JOBID=JOBnnnnn
            r'|JRN\d{4}[IWE]'           # JRN メッセージ
            r'|IEF\d{3}[IWE]'           # IEF システムメッセージ
            r'|IEA\d{3}[IWE]'           # IEA システムメッセージ
            , re.MULTILINE
        ),
        SpoolFileType.SYSPRINT: re.compile(
            r'ICE\d{3}[A-Z]|IGD\d{3}[A-Z]', re.MULTILINE
        ),
        SpoolFileType.JESJCL: re.compile(
            r'^JOB\s+STREAM=\['          # TJES JESJCL: 構文解析ツリー
            r'|^/JOB\[name='             # JESJCL ツリーフォーマット
            , re.MULTILINE
        ),
    }

    # 최대 zip 해제 크기 (100MB)
    MAX_ZIP_SIZE = 100 * 1024 * 1024
    # 개별 파일 최대 읽기 크기 (10MB)
    MAX_FILE_READ = 10 * 1024 * 1024

    async def process(
        self, zip_content: bytes, zip_filename: str
    ) -> ClassifiedFiles:
        """zip 해제 → 파일 분류 → ClassifiedFiles 반환"""
        files = self._extract_zip(zip_content)
        classified = self._classify_files(files)
        return classified

    def _extract_zip(self, zip_content: bytes) -> List[dict]:
        """zip 바이너리에서 파일 추출 (in-memory)"""
        files = []
        with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zf:
            total_size = sum(info.file_size for info in zf.infolist())
            if total_size > self.MAX_ZIP_SIZE:
                raise ValueError(
                    f"zip 전체 크기 {total_size // (1024*1024)}MB가 "
                    f"제한 {self.MAX_ZIP_SIZE // (1024*1024)}MB를 초과합니다"
                )

            for info in zf.infolist():
                if info.is_dir():
                    continue
                filename = os.path.basename(info.filename)
                if not filename:
                    continue

                content_bytes = zf.read(info.filename)[:self.MAX_FILE_READ]
                content = self._decode_content(content_bytes)

                files.append({
                    "filename": filename,
                    "size_bytes": info.file_size,
                    "content": content,
                })
        return files

    def _decode_content(self, content_bytes: bytes) -> str:
        """텍스트 디코딩 (멀티 인코딩 지원)"""
        for encoding in ["utf-8", "shift_jis", "euc-jp", "cp932", "latin-1"]:
            try:
                return content_bytes.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return content_bytes.decode("latin-1", errors="replace")

    def _classify_files(self, files: List[dict]) -> ClassifiedFiles:
        """2단계 분류: 파일명 → 콘텐츠 패턴"""
        classified_list = []

        for f in files:
            file_type, method = self._classify_single(f["filename"], f["content"])
            cf = ClassifiedFile(
                filename=f["filename"],
                file_type=file_type,
                size_bytes=f["size_bytes"],
                content=f["content"],
                detection_method=method,
            )
            classified_list.append(cf)

        # 유형별 그룹핑
        result = ClassifiedFiles(
            total_files=len(classified_list),
            files=classified_list,
        )
        for cf in classified_list:
            getattr(result, f"{cf.file_type.value}_files").append(cf)

        return result

    def _classify_single(self, filename: str, content: str) -> tuple:
        """단일 파일 분류 (type, method)"""
        # Stage 1: 파일명 패턴
        for ftype, patterns in self.FILENAME_PATTERNS.items():
            for pattern in patterns:
                if pattern.match(filename):
                    return ftype, "filename"

        # Stage 2: 콘텐츠 패턴 (첫 200줄)
        head = "\n".join(content.split("\n")[:200])
        for ftype, pattern in self.CONTENT_PATTERNS.items():
            if pattern.search(head):
                return ftype, "content_pattern"

        return SpoolFileType.UNKNOWN, "fallback"
