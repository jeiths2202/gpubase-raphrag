"""JCL Job Failure Diagnosis Router

Endpoints:
  POST /api/v1/jcl-diagnosis/analyze   - zip 업로드 → SSE 스트리밍 진단
  POST /api/v1/jcl-diagnosis/analyze-text - 텍스트 직접 입력 → SSE 진단 (Phase 2)
  GET  /api/v1/jcl-diagnosis/{diagnosis_id}/report - HTML 리포트 조회
"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse

from app.api.core.deps import get_current_user
from app.api.models.jcl_diagnosis import JCLDiagnosisRequest
from app.api.services.jcl_diagnosis import get_jcl_diagnosis_orchestrator


router = APIRouter(prefix="/jcl-diagnosis", tags=["JCL Diagnosis"])


@router.post("/analyze")
async def analyze_job_failure(
    file: UploadFile = File(..., description="JOB 출력 zip 파일"),
    message: str = Form(default=None, description="追加質問"),
    language: str = Form(default="ja", description="応答言語: ja|ko|en"),
    current_user: dict = Depends(get_current_user),
):
    """zip ファイルアップロード → JOB障害診断 (SSE ストリーミング)

    multipart/form-data:
      - file: zip ファイル (必須)
      - message: 追加質問/コンテキスト (任意)
      - language: ja|ko|en (デフォルト: ja)
    """
    zip_content = await file.read()
    request = JCLDiagnosisRequest(message=message, language=language)
    orchestrator = get_jcl_diagnosis_orchestrator()

    async def generate():
        async for event in orchestrator.stream_diagnosis(
            zip_content=zip_content,
            zip_filename=file.filename or "unknown.zip",
            request=request,
            user_id=current_user.get("user_id"),
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze-text")
async def analyze_job_failure_text(
    request: JCLDiagnosisRequest,
    current_user: dict = Depends(get_current_user),
):
    """テキスト直接入力 → 診断 (Phase 2で実装予定)"""
    return {"status": "not_implemented", "message": "Phase 2で実装予定"}


@router.get(
    "/{diagnosis_id}/report",
    response_class=HTMLResponse,
    summary="HTML診断レポート取得",
)
async def get_diagnosis_report(
    diagnosis_id: str,
    current_user: dict = Depends(get_current_user),
):
    """診断ID → 自己完結型HTMLレポート

    SSEストリーミング完了後、1時間以内にアクセス可能。
    """
    orchestrator = get_jcl_diagnosis_orchestrator()
    html = orchestrator.get_cached_report_html(diagnosis_id)
    if html is None:
        raise HTTPException(
            status_code=404,
            detail=f"Report not found or expired: {diagnosis_id}",
        )
    return HTMLResponse(content=html)
