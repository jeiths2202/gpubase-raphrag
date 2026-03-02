"""ABEND 코드 레지스트리

주요 System ABEND 코드의 설명/원인/대처 방안 매핑.
이 레지스트리는 LLM을 거치지 않는 즉시 참조용입니다.

참조: IBM System Codes + OpenFrame 호환 코드
"""

ABEND_REGISTRY: dict = {
    # ─── Data Exceptions ──────────────────────
    "S0C1": {
        "description": "Operation Exception",
        "cause": "유효하지 않은 기계어 명령 실행 시도",
        "common_causes": [
            "잘못된 프로그램 진입점",
            "모듈이 올바르게 링크되지 않음",
            "CSECT 이름 불일치"
        ],
    },
    "S0C4": {
        "description": "Protection Exception (Storage Violation)",
        "cause": "할당되지 않은 메모리 영역 접근",
        "common_causes": [
            "배열 인덱스 초과 (COBOL OCCURS)",
            "WORKING-STORAGE 초기화 누락",
            "GETMAIN/FREEMAIN 불일치",
            "잘못된 포인터 사용"
        ],
    },
    "S0C7": {
        "description": "Data Exception",
        "cause": "숫자 연산 시 비숫자 데이터 사용",
        "common_causes": [
            "MOVE/COMPUTE에 SPACE가 포함된 변수",
            "파일 레이아웃과 COPYBOOK 불일치",
            "초기화되지 않은 숫자 변수",
            "EBCDIC/ASCII 변환 오류"
        ],
    },
    "S013": {
        "description": "Conflicting DCB Parameters",
        "cause": "DD 문의 DCB 파라미터와 프로그램의 DCB가 불일치",
        "common_causes": [
            "LRECL/BLKSIZE 불일치",
            "RECFM 불일치 (F vs V)",
            "데이터셋 존재하지 않음"
        ],
    },
    "S0CB": {
        "description": "Floating Point Division by Zero",
        "cause": "부동소수점 0으로 나누기",
        "common_causes": ["COMPUTE 문에서 0으로 나누기"],
    },
    "S222": {
        "description": "Job Cancelled by Operator",
        "cause": "운영자가 JOB을 CANCEL 명령으로 취소",
        "common_causes": ["무한 루프 감지", "리소스 과다 사용"],
    },
    "S322": {
        "description": "Time Limit Exceeded",
        "cause": "JOB/STEP TIME 파라미터 초과",
        "common_causes": [
            "무한 루프",
            "대용량 데이터 처리 시 TIME 부족",
            "TIME=1440 지정 필요"
        ],
    },
    "S806": {
        "description": "Module Not Found",
        "cause": "EXEC PGM= 또는 CALL 대상 모듈이 라이브러리에 없음",
        "common_causes": [
            "프로그램명 오타",
            "STEPLIB/JOBLIB DD 누락",
            "라이브러리 연결 누락 (LKED 실패)"
        ],
    },
    "S837": {
        "description": "End of Volume / Dataset Full",
        "cause": "데이터셋에 할당된 공간 초과",
        "common_causes": [
            "SPACE 파라미터 부족",
            "2차 할당 미지정",
            "SMS 스토리지 그룹 Full"
        ],
    },
    "S913": {
        "description": "Security Authorization Failure",
        "cause": "RACF/TACF 보안 인증 실패",
        "common_causes": [
            "데이터셋 접근 권한 없음",
            "TACF 프로파일 미등록",
            "USER ID 권한 불일치"
        ],
    },
    "SB37": {
        "description": "Dataset Space Exhausted (End of Volume)",
        "cause": "데이터셋 공간 부족 (볼륨 끝)",
        "common_causes": [
            "SPACE 1차/2차 할당 부족",
            "볼륨에 여유 공간 없음"
        ],
    },
    "SD37": {
        "description": "Dataset Space Exhausted (No Secondary)",
        "cause": "2차 할당 미지정 상태에서 공간 부족",
        "common_causes": ["SPACE 2차 할당 추가 필요"],
    },
    "SE37": {
        "description": "Dataset Space Exhausted (Max Extents)",
        "cause": "최대 Extent 수 초과",
        "common_causes": [
            "Extent 수 제한 도달 (최대 16)",
            "데이터셋 재구성 필요"
        ],
    },
}
