"""
Internationalization (i18n) for CLI Agent

Provides multilingual message support for Korean, English, and Japanese.
"""

from typing import Dict

# CLI Messages in multiple languages
MESSAGES: Dict[str, Dict[str, str]] = {
    "ko": {
        # Login/Session
        "session_restored": "세션이 복원되었습니다",
        "logged_in_as": "{user}(으)로 로그인했습니다",
        "login_failed": "로그인에 실패했습니다. 자격 증명을 확인하세요.",
        "login_attempts_remaining": "로그인 실패. {count}회 시도 남음.",
        "dev_mode_trying": "개발 모드: 기본 자격 증명으로 시도 중...",
        "using_env_credentials": "환경 변수에서 자격 증명을 사용합니다...",
        "auth_required": "인증이 필요합니다. KMS_USERNAME 및 KMS_PASSWORD 환경 변수를 설정하세요.",
        "goodbye": "안녕히 가세요!",

        # IMS Session
        "ims_session_valid": "유효한 IMS 세션을 사용하여 자동 로그인합니다",
        "ims_session_checking": "IMS 세션 상태를 확인 중...",
        "ims_session_invalid": "IMS 세션이 만료되었거나 유효하지 않습니다",
        "ims_not_configured": "IMS 자격 증명이 구성되지 않았습니다. /ims-login으로 로그인하세요.",
        "ims_login_required": "IMS 에이전트를 사용하려면 먼저 /ims-login으로 로그인하세요.",
        "ims_login_prompt": "IMS 로그인",
        "ims_username": "IMS 사용자명",
        "ims_password": "IMS 비밀번호",
        "ims_login_success": "IMS 로그인 성공",
        "ims_login_failed": "IMS 로그인 실패: {error}",
        "ims_logout_success": "IMS 로그아웃 성공",
        "ims_logout_failed": "IMS 로그아웃 실패",
        "ims_validating": "IMS 자격 증명 검증 중...",
        "ims_connected": "IMS에 연결됨",
        "ims_disconnected": "IMS 연결 끊김",

        # Commands
        "help_message": "사용 가능한 명령어에 대해 /help를 입력하세요.",
        "unknown_command": "알 수 없는 명령어: {cmd}. /help를 입력하여 사용 가능한 명령어를 확인하세요.",
        "agent_switched": "에이전트 전환됨",
        "new_session_started": "새 세션이 시작되었습니다",
        "current_agent": "현재 에이전트: {agent}",
        "available_agents": "사용 가능: {agents}",

        # Status
        "status_server": "서버",
        "status_agent": "에이전트",
        "status_language": "언어",
        "status_connected": "연결됨",
        "status_disconnected": "연결 끊김",
        "status_user": "사용자",
        "status_session": "세션",
        "status_ims": "IMS 상태",

        # Errors
        "connection_error": "서버에 연결할 수 없습니다: {url}",
        "timeout_error": "요청 시간이 초과되었습니다",
        "api_error": "API 오류: {code}",
        "session_expired": "세션이 만료되었습니다. 다시 로그인하세요.",

        # Thinking/Tools
        "thinking": "분석 중...",
        "processing_results": "결과 처리 중...",
        "tool_result": "도구 결과: {size} 자",
    },
    "en": {
        # Login/Session
        "session_restored": "Session restored",
        "logged_in_as": "Logged in as {user}",
        "login_failed": "Login failed. Please check your credentials.",
        "login_attempts_remaining": "Login failed. {count} attempts remaining.",
        "dev_mode_trying": "Development mode: trying default credentials...",
        "using_env_credentials": "Using credentials from environment...",
        "auth_required": "Authentication required. Set KMS_USERNAME and KMS_PASSWORD environment variables.",
        "goodbye": "Goodbye!",

        # IMS Session
        "ims_session_valid": "Using valid session for auto-login",
        "ims_session_checking": "Checking IMS session status...",
        "ims_session_invalid": "IMS session expired or invalid",
        "ims_not_configured": "IMS credentials not configured. Login with /ims-login.",
        "ims_login_required": "Please login with /ims-login first to use IMS agent.",
        "ims_login_prompt": "IMS Login",
        "ims_username": "IMS Username",
        "ims_password": "IMS Password",
        "ims_login_success": "IMS login successful",
        "ims_login_failed": "IMS login failed: {error}",
        "ims_logout_success": "IMS logout successful",
        "ims_logout_failed": "IMS logout failed",
        "ims_validating": "Validating IMS credentials...",
        "ims_connected": "Connected to IMS",
        "ims_disconnected": "IMS disconnected",

        # Commands
        "help_message": "Type /help for available commands.",
        "unknown_command": "Unknown command: {cmd}. Type /help for available commands.",
        "agent_switched": "Agent switched",
        "new_session_started": "New session started",
        "current_agent": "Current agent: {agent}",
        "available_agents": "Available: {agents}",

        # Status
        "status_server": "Server",
        "status_agent": "Agent",
        "status_language": "Language",
        "status_connected": "Connected",
        "status_disconnected": "Disconnected",
        "status_user": "User",
        "status_session": "Session",
        "status_ims": "IMS Status",

        # Errors
        "connection_error": "Cannot connect to server at {url}",
        "timeout_error": "Request timed out",
        "api_error": "API error: {code}",
        "session_expired": "Session expired. Please login again.",

        # Thinking/Tools
        "thinking": "Analyzing...",
        "processing_results": "Processing results...",
        "tool_result": "Tool result: {size} chars",
    },
    "ja": {
        # Login/Session
        "session_restored": "セッションが復元されました",
        "logged_in_as": "{user}としてログインしました",
        "login_failed": "ログインに失敗しました。認証情報を確認してください。",
        "login_attempts_remaining": "ログイン失敗。残り{count}回の試行。",
        "dev_mode_trying": "開発モード：デフォルトの認証情報で試行中...",
        "using_env_credentials": "環境変数から認証情報を使用しています...",
        "auth_required": "認証が必要です。KMS_USERNAMEおよびKMS_PASSWORD環境変数を設定してください。",
        "goodbye": "さようなら！",

        # IMS Session
        "ims_session_valid": "有効なセッションで自動ログインします",
        "ims_session_checking": "IMSセッションステータスを確認中...",
        "ims_session_invalid": "IMSセッションが期限切れまたは無効です",
        "ims_not_configured": "IMS認証情報が設定されていません。/ims-loginでログインしてください。",
        "ims_login_required": "IMSエージェントを使用するには、まず/ims-loginでログインしてください。",
        "ims_login_prompt": "IMSログイン",
        "ims_username": "IMSユーザー名",
        "ims_password": "IMSパスワード",
        "ims_login_success": "IMSログイン成功",
        "ims_login_failed": "IMSログイン失敗：{error}",
        "ims_logout_success": "IMSログアウト成功",
        "ims_logout_failed": "IMSログアウト失敗",
        "ims_validating": "IMS認証情報を検証中...",
        "ims_connected": "IMSに接続済み",
        "ims_disconnected": "IMS切断",

        # Commands
        "help_message": "利用可能なコマンドについては/helpと入力してください。",
        "unknown_command": "不明なコマンド：{cmd}。/helpで利用可能なコマンドを確認してください。",
        "agent_switched": "エージェント切替",
        "new_session_started": "新しいセッションが開始されました",
        "current_agent": "現在のエージェント：{agent}",
        "available_agents": "利用可能：{agents}",

        # Status
        "status_server": "サーバー",
        "status_agent": "エージェント",
        "status_language": "言語",
        "status_connected": "接続済み",
        "status_disconnected": "切断",
        "status_user": "ユーザー",
        "status_session": "セッション",
        "status_ims": "IMSステータス",

        # Errors
        "connection_error": "サーバーに接続できません：{url}",
        "timeout_error": "リクエストがタイムアウトしました",
        "api_error": "APIエラー：{code}",
        "session_expired": "セッションが期限切れです。再度ログインしてください。",

        # Thinking/Tools
        "thinking": "分析中...",
        "processing_results": "結果を処理中...",
        "tool_result": "ツール結果：{size}文字",
    }
}


class I18n:
    """Internationalization helper class"""

    def __init__(self, language: str = "ko"):
        self.language = language if language in MESSAGES else "ko"
        self._messages = MESSAGES[self.language]

    def set_language(self, language: str):
        """Change current language"""
        if language in MESSAGES:
            self.language = language
            self._messages = MESSAGES[language]

    def t(self, key: str, **kwargs) -> str:
        """Get translated message with optional formatting"""
        message = self._messages.get(key, key)
        if kwargs:
            try:
                return message.format(**kwargs)
            except KeyError:
                return message
        return message

    def __call__(self, key: str, **kwargs) -> str:
        """Shorthand for t()"""
        return self.t(key, **kwargs)


# Global instance
_i18n: I18n = None


def get_i18n(language: str = "ko") -> I18n:
    """Get or create global i18n instance"""
    global _i18n
    if _i18n is None or _i18n.language != language:
        _i18n = I18n(language)
    return _i18n
