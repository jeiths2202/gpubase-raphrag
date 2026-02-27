"""JCL Diagnosis Report i18n Labels

HTML 템플릿에서 사용하는 모든 UI 문자열의 다국어 매핑.
3개 로케일(ja/ko/en)은 반드시 동일한 키셋을 가져야 합니다.
"""

LABELS: dict[str, dict[str, str]] = {
    "ja": {
        # ─── Locale ───
        "locale_code": "ja-JP",

        # ─── Header ───
        "report_badge": "障害診断レポート",
        "report_title": "JCLジョブ障害診断レポート",
        "label_created_at": "作成日時",
        "label_diagnosis": "診断",

        # ─── Section Headers ───
        "section_job_summary": "ジョブ実行概要",
        "section_step_flow": "STEP実行フロー",
        "section_error_diagnosis": "障害原因分析",
        "section_resolutions": "対処方法",
        "section_related_docs": "関連ドキュメント",
        "section_similar_cases": "類似障害事例",

        # ─── Job Summary ───
        "label_submit_time": "投入時刻",
        "label_elapsed": "経過時間",
        "label_step_exec": "STEP実行",
        "label_submitter": "投入元",
        "label_end": "終了",
        "label_stopped_at_fmt": "STEP{n}にて停止",

        # ─── Step Flow ───
        "step_status_completed": "✓",
        "step_status_failed": "！",
        "step_status_skipped": "⏭",
        "label_skip": "SKIP",

        # ─── Error Diagnosis ───
        "label_root_cause": "原因分析結果",
        "label_impact_title": "業務影響",

        # ─── Resolutions ───
        "label_copy": "コピー",
        "label_copied": "✓ コピーしました",

        # ─── Similar Cases ───
        "case_event_label": "事象：",
        "case_resolution_label": "解決策：",

        # ─── Footer ───
        "label_print": "印刷",
        "label_markdown_export": "Markdown出力",
        "label_consult_expert": "専門家に相談",
        "alert_expert": "専門家連携機能はKMSシステム統合時に有効化されます。",

        # ─── Markdown Modal ───
        "modal_title": "Markdown形式でエクスポート",
        "modal_close": "閉じる",
        "modal_save_md": ".mdファイル保存",
        "modal_copy_clipboard": "クリップボードにコピー",

        # ─── Markdown Content ───
        "md_table_item": "項目",
        "md_table_content": "内容",
        "md_report_id": "レポートID",
        "md_created_at": "作成日時",
        "md_diagnosis_agent": "診断エージェント",
        "md_target_system": "対象システム",
        "md_job_name": "JOB名",
        "md_class_priority": "CLASS / Priority",
        "md_submit_time": "投入時刻",
        "md_end_time": "終了時刻",
        "md_elapsed": "経過時間",
        "md_submitter": "投入元",
        "md_step_exec": "STEP実行",
        "md_stopped_at_fmt": "STEP{n}にて停止",
        "md_step_col": "STEP",
        "md_name_col": "名称",
        "md_program_col": "プログラム",
        "md_status_col": "状態",
        "md_rc_col": "RC",
        "md_elapsed_col": "経過",
        "md_step_ok": "✅ 正常",
        "md_step_abend": "⚠️ 異常終了",
        "md_step_skip": "⏭ スキップ",
        "md_error_info": "エラー情報",
        "md_error_code": "エラーコード",
        "md_error_type": "種別",
        "md_failed_step": "障害STEP",
        "md_target_program": "対象プログラム",
        "md_severity": "重要度",
        "md_sysmsg": "SYSMSGメッセージ",
        "md_root_cause": "原因分析結果",
        "md_impact": "業務影響",
        "md_resolution_prefix": "対処",
        "md_priority_label": "優先度",
        "md_relevance": "関連度",
        "md_case_job": "対象JOB",
        "md_case_error": "エラーコード",
        "md_case_event": "事象",
        "md_case_resolution": "解決策",
        "md_footer_auto_fmt": "本レポートは{agent}により自動生成されました。",
        "md_report_filename_fmt": "{rid}_障害診断レポート.md",
    },

    "ko": {
        # ─── Locale ───
        "locale_code": "ko-KR",

        # ─── Header ───
        "report_badge": "장애 진단 리포트",
        "report_title": "JCL 작업 장애 진단 리포트",
        "label_created_at": "작성일시",
        "label_diagnosis": "진단",

        # ─── Section Headers ───
        "section_job_summary": "작업 실행 개요",
        "section_step_flow": "STEP 실행 흐름",
        "section_error_diagnosis": "장애 원인 분석",
        "section_resolutions": "대처 방법",
        "section_related_docs": "관련 문서",
        "section_similar_cases": "유사 장애 사례",

        # ─── Job Summary ───
        "label_submit_time": "투입 시각",
        "label_elapsed": "경과 시간",
        "label_step_exec": "STEP 실행",
        "label_submitter": "투입원",
        "label_end": "종료",
        "label_stopped_at_fmt": "STEP{n}에서 중단",

        # ─── Step Flow ───
        "step_status_completed": "✓",
        "step_status_failed": "！",
        "step_status_skipped": "⏭",
        "label_skip": "SKIP",

        # ─── Error Diagnosis ───
        "label_root_cause": "원인 분석 결과",
        "label_impact_title": "업무 영향",

        # ─── Resolutions ───
        "label_copy": "복사",
        "label_copied": "✓ 복사됨",

        # ─── Similar Cases ───
        "case_event_label": "상황：",
        "case_resolution_label": "해결책：",

        # ─── Footer ───
        "label_print": "인쇄",
        "label_markdown_export": "Markdown 출력",
        "label_consult_expert": "전문가 상담",
        "alert_expert": "전문가 연계 기능은 KMS 시스템 통합 시 활성화됩니다.",

        # ─── Markdown Modal ───
        "modal_title": "Markdown 형식 내보내기",
        "modal_close": "닫기",
        "modal_save_md": ".md 파일 저장",
        "modal_copy_clipboard": "클립보드에 복사",

        # ─── Markdown Content ───
        "md_table_item": "항목",
        "md_table_content": "내용",
        "md_report_id": "리포트 ID",
        "md_created_at": "작성일시",
        "md_diagnosis_agent": "진단 에이전트",
        "md_target_system": "대상 시스템",
        "md_job_name": "JOB명",
        "md_class_priority": "CLASS / Priority",
        "md_submit_time": "투입 시각",
        "md_end_time": "종료 시각",
        "md_elapsed": "경과 시간",
        "md_submitter": "투입원",
        "md_step_exec": "STEP 실행",
        "md_stopped_at_fmt": "STEP{n}에서 중단",
        "md_step_col": "STEP",
        "md_name_col": "명칭",
        "md_program_col": "프로그램",
        "md_status_col": "상태",
        "md_rc_col": "RC",
        "md_elapsed_col": "경과",
        "md_step_ok": "✅ 정상",
        "md_step_abend": "⚠️ 비정상 종료",
        "md_step_skip": "⏭ 스킵",
        "md_error_info": "에러 정보",
        "md_error_code": "에러 코드",
        "md_error_type": "유형",
        "md_failed_step": "장애 STEP",
        "md_target_program": "대상 프로그램",
        "md_severity": "중요도",
        "md_sysmsg": "SYSMSG 메시지",
        "md_root_cause": "원인 분석 결과",
        "md_impact": "업무 영향",
        "md_resolution_prefix": "대처",
        "md_priority_label": "우선도",
        "md_relevance": "관련도",
        "md_case_job": "대상 JOB",
        "md_case_error": "에러 코드",
        "md_case_event": "상황",
        "md_case_resolution": "해결책",
        "md_footer_auto_fmt": "본 리포트는 {agent}에 의해 자동 생성되었습니다.",
        "md_report_filename_fmt": "{rid}_장애진단리포트.md",
    },

    "en": {
        # ─── Locale ───
        "locale_code": "en-US",

        # ─── Header ───
        "report_badge": "Failure Diagnosis Report",
        "report_title": "JCL Job Failure Diagnosis Report",
        "label_created_at": "Created",
        "label_diagnosis": "Diagnosis",

        # ─── Section Headers ───
        "section_job_summary": "Job Execution Summary",
        "section_step_flow": "Step Execution Flow",
        "section_error_diagnosis": "Error Cause Analysis",
        "section_resolutions": "Resolutions",
        "section_related_docs": "Related Documents",
        "section_similar_cases": "Similar Cases",

        # ─── Job Summary ───
        "label_submit_time": "Submit Time",
        "label_elapsed": "Elapsed Time",
        "label_step_exec": "Steps Executed",
        "label_submitter": "Submitter",
        "label_end": "End",
        "label_stopped_at_fmt": "Stopped at STEP{n}",

        # ─── Step Flow ───
        "step_status_completed": "✓",
        "step_status_failed": "！",
        "step_status_skipped": "⏭",
        "label_skip": "SKIP",

        # ─── Error Diagnosis ───
        "label_root_cause": "Root Cause Analysis",
        "label_impact_title": "Business Impact",

        # ─── Resolutions ───
        "label_copy": "Copy",
        "label_copied": "✓ Copied",

        # ─── Similar Cases ───
        "case_event_label": "Incident: ",
        "case_resolution_label": "Resolution: ",

        # ─── Footer ───
        "label_print": "Print",
        "label_markdown_export": "Markdown Export",
        "label_consult_expert": "Consult Expert",
        "alert_expert": "Expert consultation will be available when KMS system integration is complete.",

        # ─── Markdown Modal ───
        "modal_title": "Export as Markdown",
        "modal_close": "Close",
        "modal_save_md": "Save .md File",
        "modal_copy_clipboard": "Copy to Clipboard",

        # ─── Markdown Content ───
        "md_table_item": "Item",
        "md_table_content": "Content",
        "md_report_id": "Report ID",
        "md_created_at": "Created",
        "md_diagnosis_agent": "Diagnosis Agent",
        "md_target_system": "Target System",
        "md_job_name": "Job Name",
        "md_class_priority": "CLASS / Priority",
        "md_submit_time": "Submit Time",
        "md_end_time": "End Time",
        "md_elapsed": "Elapsed Time",
        "md_submitter": "Submitter",
        "md_step_exec": "Steps Executed",
        "md_stopped_at_fmt": "Stopped at STEP{n}",
        "md_step_col": "STEP",
        "md_name_col": "Name",
        "md_program_col": "Program",
        "md_status_col": "Status",
        "md_rc_col": "RC",
        "md_elapsed_col": "Elapsed",
        "md_step_ok": "✅ Normal",
        "md_step_abend": "⚠️ ABEND",
        "md_step_skip": "⏭ Skipped",
        "md_error_info": "Error Information",
        "md_error_code": "Error Code",
        "md_error_type": "Type",
        "md_failed_step": "Failed Step",
        "md_target_program": "Target Program",
        "md_severity": "Severity",
        "md_sysmsg": "SYSMSG Messages",
        "md_root_cause": "Root Cause Analysis",
        "md_impact": "Business Impact",
        "md_resolution_prefix": "Resolution",
        "md_priority_label": "Priority",
        "md_relevance": "Relevance",
        "md_case_job": "Target Job",
        "md_case_error": "Error Code",
        "md_case_event": "Incident",
        "md_case_resolution": "Resolution",
        "md_footer_auto_fmt": "This report was auto-generated by {agent}.",
        "md_report_filename_fmt": "{rid}_diagnosis_report.md",
    },
}


def get_labels(language: str) -> dict[str, str]:
    """지정된 언어의 라벨 딕셔너리 반환. 미지원 언어는 ja 폴백."""
    return LABELS.get(language, LABELS["ja"])


def validate_label_keys() -> bool:
    """3개 로케일의 키셋이 동일한지 검증 (테스트용)."""
    ja_keys = set(LABELS["ja"].keys())
    ko_keys = set(LABELS["ko"].keys())
    en_keys = set(LABELS["en"].keys())
    return ja_keys == ko_keys == en_keys
