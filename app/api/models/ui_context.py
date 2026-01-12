"""
UI Context Models

Defines Pydantic models for UI context that is shared between
frontend and backend for context-aware AI responses.

These models are used to:
- Validate UI context received from frontend
- Filter context based on user role
- Provide type safety for context processing
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PageType(str, Enum):
    """Page types in the application"""
    HOME = "home"
    KNOWLEDGE = "knowledge"
    FAQ = "faq"
    IMS = "ims"
    AGENT = "agent"
    DOCUMENTS = "documents"
    SETTINGS = "settings"
    ADMIN = "admin"
    AI_STUDIO = "ai-studio"
    EXTERNAL_PORTAL = "external-portal"
    UNKNOWN = "unknown"


class SelectedItemType(str, Enum):
    """Types of items that can be selected"""
    FAQ_ITEM = "faq_item"
    DOCUMENT = "document"
    IMS_ISSUE = "ims_issue"
    KNOWLEDGE_ARTICLE = "knowledge_article"
    AGENT_CONVERSATION = "agent_conversation"
    SEARCH_RESULT = "search_result"
    NONE = "none"


class SelectedItem(BaseModel):
    """Selected item with content"""
    type: SelectedItemType = Field(..., description="Type of the selected item")
    id: str = Field(..., description="Unique identifier")
    title: str = Field(..., description="Display title")
    content: Optional[str] = Field(None, description="Full content (may be filtered by role)")
    summary: Optional[str] = Field(None, description="Brief summary (always visible)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class PageMetadata(BaseModel):
    """Page-specific metadata"""
    faq_category: Optional[str] = Field(None, description="FAQ category if on FAQ page")
    search_query: Optional[str] = Field(None, description="Search query if searching")
    active_filters: Optional[Dict[str, Any]] = Field(None, description="Active filters")
    ims_job_id: Optional[str] = Field(None, description="IMS job ID if crawling")
    document_path: Optional[str] = Field(None, description="Document folder path")

    class Config:
        extra = "allow"  # Allow additional fields


class UIContext(BaseModel):
    """
    Complete UI Context sent from frontend to AI.

    This context allows the AI assistant to understand:
    - What page the user is currently viewing
    - What item/content is selected or expanded
    - User's language and theme preferences
    - User's permission scope for role-based filtering
    """
    current_page: PageType = Field(..., description="Current page identifier")
    page_title: str = Field(..., description="Human-readable page title")
    page_metadata: Optional[PageMetadata] = Field(None, description="Page-specific metadata")
    selected_item: Optional[SelectedItem] = Field(None, description="Currently selected/expanded item")
    visible_components: List[str] = Field(default_factory=list, description="List of visible UI components")
    language: str = Field("ko", description="User's preferred language")
    theme: str = Field("dark", description="Current theme")
    user_permission_scope: str = Field("user", description="User's permission scope")
    captured_at: Optional[str] = Field(None, description="Timestamp when context was captured")

    class Config:
        use_enum_values = True


class FilteredUIContext(BaseModel):
    """
    Filtered context for non-admin users.
    Content fields are redacted to protect sensitive information.
    """
    current_page: PageType
    page_title: str
    selected_item_summary: Optional[Dict[str, Any]] = Field(
        None,
        description="Summary of selected item (content redacted for non-admin)"
    )
    visible_components: List[str] = Field(default_factory=list)
    language: str = "ko"
    theme: str = "dark"
    user_permission_scope: str = "user"

    class Config:
        use_enum_values = True


# Page titles for reference
PAGE_TITLES = {
    PageType.HOME: "Home",
    PageType.KNOWLEDGE: "Knowledge Base",
    PageType.FAQ: "FAQ",
    PageType.IMS: "IMS Search",
    PageType.AGENT: "AI Agent",
    PageType.DOCUMENTS: "Documents",
    PageType.SETTINGS: "Settings",
    PageType.ADMIN: "Admin Dashboard",
    PageType.AI_STUDIO: "AI Studio",
    PageType.EXTERNAL_PORTAL: "External Portal",
    PageType.UNKNOWN: "Unknown",
}

# Detailed page descriptions for context-aware AI
PAGE_DESCRIPTIONS = {
    PageType.HOME: """The Home Dashboard page displays:
- System overview and quick stats (document count, query count, user activity)
- Recent activity feed showing latest queries and document uploads
- Quick action buttons for common tasks
- System health indicators""",

    PageType.KNOWLEDGE: """The Knowledge Base page allows users to:
- Browse and search the knowledge article library
- View article details, categories, and tags
- Filter articles by category, date, or author
- Access linked documents and related content""",

    PageType.FAQ: """The FAQ (Frequently Asked Questions) page shows:
- List of common questions organized by category
- Search functionality to find specific answers
- Ability to view full answer content
- Related questions and helpful resources""",

    PageType.IMS: """The IMS (Issue Management System) Search page provides:
- Search interface for bug reports and issues
- Filter by status, priority, assignee, and date
- View issue details including description, steps to reproduce
- Link issues to knowledge articles""",

    PageType.AGENT: """The AI Agent page is a full-featured chat interface with:
- Multiple agent types (RAG, IMS, Vision, Code, Planner)
- Streaming responses with tool call visualization
- Conversation history management
- Source document display and artifact panel""",

    PageType.DOCUMENTS: """The Documents management page allows:
- Upload and manage documents for the RAG system
- View document metadata, chunk counts, and indexing status
- Organize documents by folder or category
- Monitor document processing pipeline""",

    PageType.SETTINGS: """The Settings page provides configuration for:
- User profile and preferences
- Language and theme settings
- Notification preferences
- API key management
- External resource connections""",

    PageType.ADMIN: """The Admin Dashboard shows system administration features:
- User management (create, edit, delete users)
- System analytics and usage metrics
- RAG configuration and governance settings
- Audit logs and security monitoring
- Performance metrics and health status""",

    PageType.AI_STUDIO: """The AI Studio page provides advanced AI features:
- Vision LLM for image and chart analysis
- Sequential pipeline for multi-step document processing
- Code generation and analysis tools
- Custom prompt templates""",

    PageType.EXTERNAL_PORTAL: """The External Portal page manages:
- Connected external resources (Notion, GitHub, Google Drive, Confluence)
- OAuth connection management
- Sync status and content indexing
- Resource-specific search and retrieval""",

    PageType.UNKNOWN: "Unknown page - no specific context available.",
}

# Detailed usage guides for each page (how to use)
PAGE_USAGE_GUIDES = {
    PageType.HOME: """홈 대시보드 사용법:

1. **시스템 현황 확인**
   - 상단의 통계 카드에서 전체 문서 수, 쿼리 수, 사용자 활동을 한눈에 확인하세요
   - 각 카드를 클릭하면 상세 정보 페이지로 이동합니다

2. **최근 활동 모니터링**
   - 최근 활동 피드에서 최신 쿼리와 문서 업로드 내역을 확인하세요
   - 항목을 클릭하면 해당 내용의 상세 정보를 볼 수 있습니다

3. **빠른 작업 실행**
   - 빠른 작업 버튼을 사용하여 자주 사용하는 기능에 빠르게 접근하세요
   - 문서 업로드, 새 쿼리, 설정 등에 바로 접근할 수 있습니다

4. **시스템 상태 확인**
   - 하단의 시스템 상태 표시기에서 각 서비스의 상태를 확인하세요
   - 빨간색 표시가 있으면 해당 서비스에 문제가 있을 수 있습니다""",

    PageType.KNOWLEDGE: """지식 베이스 사용법:

1. **문서 검색**
   - 상단 검색창에 키워드를 입력하여 문서를 검색하세요
   - 자연어로 질문을 입력해도 관련 문서를 찾을 수 있습니다

2. **카테고리 필터링**
   - 좌측 카테고리 메뉴에서 원하는 카테고리를 선택하세요
   - 여러 카테고리를 조합하여 필터링할 수 있습니다

3. **문서 상세 보기**
   - 문서 제목을 클릭하면 전체 내용을 볼 수 있습니다
   - 관련 문서와 태그도 함께 표시됩니다

4. **문서 관리 (관리자)**
   - 새 문서 추가, 편집, 삭제가 가능합니다
   - 문서에 태그와 카테고리를 지정할 수 있습니다""",

    PageType.FAQ: """FAQ 페이지 사용법:

1. **질문 검색**
   - 검색창에 키워드를 입력하여 관련 FAQ를 찾으세요
   - 자주 묻는 질문은 상단에 고정되어 있습니다

2. **카테고리별 탐색**
   - 카테고리 탭을 클릭하여 분류별로 FAQ를 확인하세요
   - 각 카테고리에는 관련 질문들이 모여 있습니다

3. **답변 확인**
   - 질문을 클릭하면 답변이 펼쳐집니다
   - 도움이 되었는지 피드백을 남길 수 있습니다

4. **관련 질문 확인**
   - 답변 하단에서 관련된 다른 질문들을 확인하세요
   - 추가 도움이 필요하면 AI 어시스턴트에게 질문하세요""",

    PageType.IMS: """IMS 검색 사용법:

1. **이슈 검색**
   - 검색창에 자연어로 이슈를 검색하세요
   - 예: "로그인 오류", "성능 저하 문제" 등

2. **필터 사용**
   - 상태(열림/닫힘), 우선순위, 담당자별로 필터링하세요
   - 날짜 범위를 지정하여 특정 기간의 이슈를 찾을 수 있습니다

3. **이슈 상세 보기**
   - 이슈를 클릭하면 상세 정보를 볼 수 있습니다
   - 재현 단계, 첨부 파일, 댓글 등을 확인하세요

4. **IMS 연동 설정**
   - 처음 사용 시 IMS 계정 연동이 필요합니다
   - 설정에서 IMS 서버 URL과 인증 정보를 입력하세요""",

    PageType.AGENT: """AI 에이전트 사용법:

1. **에이전트 선택**
   - 상단 드롭다운에서 적합한 에이전트를 선택하세요
   - RAG: 문서 기반 질의응답
   - IMS: 이슈 검색 및 분석
   - Vision: 이미지/차트 분석
   - Code: 코드 생성 및 분석
   - Planner: 복잡한 작업 계획

2. **질문하기**
   - 하단 입력창에 질문을 입력하고 전송하세요
   - Shift+Enter로 여러 줄 입력이 가능합니다

3. **파일 첨부**
   - 클립 아이콘을 클릭하여 파일을 첨부할 수 있습니다
   - 첨부된 파일 내용을 기반으로 답변합니다

4. **대화 기록 관리**
   - 좌측 히스토리 패널에서 이전 대화를 확인하세요
   - 새 대화 시작 버튼으로 새 세션을 시작합니다""",

    PageType.DOCUMENTS: """문서 관리 사용법:

1. **문서 업로드**
   - '업로드' 버튼을 클릭하여 문서를 추가하세요
   - PDF, DOCX, TXT, MD 등 다양한 형식을 지원합니다
   - 드래그 앤 드롭으로도 업로드할 수 있습니다

2. **문서 상태 확인**
   - 업로드된 문서의 처리 상태를 확인하세요
   - 처리 중, 완료, 오류 상태가 표시됩니다
   - 청크 수와 인덱싱 상태도 확인할 수 있습니다

3. **문서 관리**
   - 문서를 폴더별로 정리할 수 있습니다
   - 문서 삭제 시 관련 벡터 인덱스도 함께 삭제됩니다

4. **검색 테스트**
   - 업로드된 문서로 검색 테스트를 해보세요
   - AI 어시스턴트에서 해당 문서 내용을 질문할 수 있습니다""",

    PageType.SETTINGS: """설정 페이지 사용법:

1. **프로필 설정**
   - 사용자 이름, 이메일, 프로필 사진을 변경하세요
   - 비밀번호 변경도 이 메뉴에서 가능합니다

2. **언어 및 테마**
   - 인터페이스 언어를 한국어/영어/일본어 중 선택하세요
   - 라이트/다크 테마를 선택하거나 시스템 설정을 따를 수 있습니다

3. **알림 설정**
   - 이메일 알림, 푸시 알림 등을 설정하세요
   - 알림 받을 이벤트 유형을 선택할 수 있습니다

4. **외부 연동**
   - Notion, GitHub 등 외부 서비스 연동을 설정하세요
   - API 키 관리도 이 메뉴에서 가능합니다""",

    PageType.ADMIN: """관리자 대시보드 사용법:

1. **사용자 관리**
   - 사용자 목록에서 계정을 생성, 수정, 삭제하세요
   - 역할(관리자/일반 사용자) 및 권한을 설정할 수 있습니다

2. **시스템 분석**
   - 사용량 통계, 쿼리 분석, 문서 현황을 확인하세요
   - 기간별 추이 그래프로 시스템 사용 패턴을 파악하세요

3. **RAG 설정**
   - 검색 파라미터, 청킹 설정, 모델 설정을 조정하세요
   - 거버넌스 규칙을 설정하여 응답 품질을 관리하세요

4. **감사 로그**
   - 시스템 접근 기록과 변경 이력을 확인하세요
   - 보안 이벤트 모니터링이 가능합니다""",

    PageType.AI_STUDIO: """AI 스튜디오 사용법:

1. **Vision LLM**
   - 이미지나 차트를 업로드하여 분석을 요청하세요
   - 그래프 데이터 추출, 이미지 설명 등이 가능합니다

2. **Sequential Pipeline**
   - 여러 단계의 문서 처리 파이프라인을 구성하세요
   - 추출 → 분석 → 요약 등 연속 작업을 자동화합니다

3. **코드 생성**
   - 자연어로 코드 생성을 요청하세요
   - 생성된 코드는 아티팩트 패널에서 확인하고 복사할 수 있습니다

4. **프롬프트 템플릿**
   - 자주 사용하는 프롬프트를 템플릿으로 저장하세요
   - 저장된 템플릿으로 빠르게 작업을 시작할 수 있습니다""",

    PageType.EXTERNAL_PORTAL: """외부 포털 연동 사용법:

1. **서비스 연결**
   - '연결 추가' 버튼으로 외부 서비스를 연동하세요
   - Notion, GitHub, Google Drive, Confluence를 지원합니다

2. **OAuth 인증**
   - 각 서비스의 OAuth 인증을 완료하세요
   - 인증 후 자동으로 콘텐츠 동기화가 시작됩니다

3. **동기화 관리**
   - 동기화 상태와 마지막 동기화 시간을 확인하세요
   - 수동 동기화 버튼으로 즉시 업데이트할 수 있습니다

4. **통합 검색**
   - 연동된 모든 소스에서 통합 검색이 가능합니다
   - AI 어시스턴트도 외부 소스의 정보를 활용합니다""",

    PageType.UNKNOWN: "이 페이지에 대한 사용법 정보가 없습니다. 도움이 필요하시면 관리자에게 문의하세요.",
}

# English usage guides
PAGE_USAGE_GUIDES_EN = {
    PageType.HOME: """Home Dashboard Usage Guide:

1. **Check System Status**
   - View total documents, queries, and user activity at a glance from the stat cards at the top
   - Click each card to navigate to detailed information pages

2. **Monitor Recent Activity**
   - Check the latest queries and document uploads in the recent activity feed
   - Click an item to view its detailed information

3. **Quick Actions**
   - Use quick action buttons to access frequently used features
   - Quickly access document upload, new query, settings, etc.

4. **System Health**
   - Check the status of each service in the system health indicators at the bottom
   - Red indicators may signal issues with that service""",

    PageType.KNOWLEDGE: """Knowledge Base Usage Guide:

1. **Search Documents**
   - Enter keywords in the search bar at the top to find documents
   - You can also use natural language questions to find relevant documents

2. **Filter by Category**
   - Select your desired category from the left menu
   - Combine multiple categories for more refined filtering

3. **View Document Details**
   - Click a document title to view its full content
   - Related documents and tags are also displayed

4. **Document Management (Admin)**
   - Add, edit, and delete documents
   - Assign tags and categories to documents""",

    PageType.FAQ: """FAQ Page Usage Guide:

1. **Search Questions**
   - Enter keywords in the search bar to find relevant FAQs
   - Frequently asked questions are pinned at the top

2. **Browse by Category**
   - Click category tabs to view FAQs by classification
   - Each category contains related questions

3. **View Answers**
   - Click a question to expand and view the answer
   - Leave feedback on whether it was helpful

4. **Related Questions**
   - Check related questions at the bottom of each answer
   - Ask the AI assistant if you need additional help""",

    PageType.IMS: """IMS Search Usage Guide:

1. **Search Issues**
   - Search for issues using natural language
   - Examples: "login error", "performance degradation" etc.

2. **Use Filters**
   - Filter by status (open/closed), priority, and assignee
   - Specify date ranges to find issues from specific periods

3. **View Issue Details**
   - Click an issue to view its detailed information
   - Check reproduction steps, attachments, and comments

4. **IMS Integration Setup**
   - First-time users need to set up IMS account integration
   - Enter IMS server URL and credentials in settings""",

    PageType.AGENT: """AI Agent Usage Guide:

1. **Select Agent**
   - Choose the appropriate agent from the dropdown at the top
   - RAG: Document-based Q&A
   - IMS: Issue search and analysis
   - Vision: Image/chart analysis
   - Code: Code generation and analysis
   - Planner: Complex task planning

2. **Ask Questions**
   - Enter your question in the input field at the bottom and send
   - Use Shift+Enter for multi-line input

3. **Attach Files**
   - Click the clip icon to attach files
   - Responses will be based on attached file content

4. **Manage Conversation History**
   - View previous conversations in the history panel on the left
   - Start a new session with the new conversation button""",

    PageType.DOCUMENTS: """Document Management Usage Guide:

1. **Upload Documents**
   - Click the 'Upload' button to add documents
   - Supports various formats: PDF, DOCX, TXT, MD, etc.
   - Drag and drop upload is also available

2. **Check Document Status**
   - Monitor the processing status of uploaded documents
   - Status shows: Processing, Complete, or Error
   - View chunk count and indexing status

3. **Manage Documents**
   - Organize documents by folder
   - Deleting a document also removes related vector indexes

4. **Test Search**
   - Test search with your uploaded documents
   - Ask questions about document content in the AI assistant""",

    PageType.SETTINGS: """Settings Page Usage Guide:

1. **Profile Settings**
   - Change your username, email, and profile picture
   - Password changes are also available here

2. **Language & Theme**
   - Select interface language: Korean/English/Japanese
   - Choose light/dark theme or follow system settings

3. **Notification Settings**
   - Configure email and push notifications
   - Select which event types to receive notifications for

4. **External Integrations**
   - Set up integrations with Notion, GitHub, etc.
   - API key management is also available here""",

    PageType.ADMIN: """Admin Dashboard Usage Guide:

1. **User Management**
   - Create, edit, and delete accounts from the user list
   - Set roles (admin/regular user) and permissions

2. **System Analytics**
   - View usage statistics, query analysis, and document status
   - Analyze system usage patterns with trend graphs

3. **RAG Configuration**
   - Adjust search parameters, chunking settings, and model settings
   - Set governance rules to manage response quality

4. **Audit Logs**
   - Review system access records and change history
   - Monitor security events""",

    PageType.AI_STUDIO: """AI Studio Usage Guide:

1. **Vision LLM**
   - Upload images or charts to request analysis
   - Extract graph data, describe images, etc.

2. **Sequential Pipeline**
   - Configure multi-step document processing pipelines
   - Automate sequential tasks: extraction → analysis → summarization

3. **Code Generation**
   - Request code generation using natural language
   - View and copy generated code in the artifact panel

4. **Prompt Templates**
   - Save frequently used prompts as templates
   - Quickly start tasks using saved templates""",

    PageType.EXTERNAL_PORTAL: """External Portal Integration Usage Guide:

1. **Connect Services**
   - Click 'Add Connection' to integrate external services
   - Supports Notion, GitHub, Google Drive, Confluence

2. **OAuth Authentication**
   - Complete OAuth authentication for each service
   - Content synchronization starts automatically after authentication

3. **Sync Management**
   - Check sync status and last sync time
   - Use manual sync button for immediate updates

4. **Unified Search**
   - Search across all connected sources
   - AI assistant also utilizes information from external sources""",

    PageType.UNKNOWN: "No usage guide available for this page. Please contact an administrator if you need help.",
}

# Japanese usage guides
PAGE_USAGE_GUIDES_JA = {
    PageType.HOME: """ホームダッシュボードの使い方：

1. **システム状況の確認**
   - 上部の統計カードで、ドキュメント数、クエリ数、ユーザーアクティビティを一目で確認できます
   - 各カードをクリックすると詳細情報ページに移動します

2. **最近のアクティビティの監視**
   - 最近のアクティビティフィードで、最新のクエリとドキュメントアップロード履歴を確認できます
   - 項目をクリックすると詳細情報を表示できます

3. **クイックアクション**
   - クイックアクションボタンで、よく使う機能に素早くアクセスできます
   - ドキュメントアップロード、新規クエリ、設定などに直接アクセスできます

4. **システム状態の確認**
   - 下部のシステム状態インジケーターで各サービスの状態を確認できます
   - 赤い表示がある場合、そのサービスに問題がある可能性があります""",

    PageType.KNOWLEDGE: """ナレッジベースの使い方：

1. **ドキュメント検索**
   - 上部の検索バーにキーワードを入力してドキュメントを検索できます
   - 自然言語で質問を入力しても関連ドキュメントを見つけることができます

2. **カテゴリフィルタリング**
   - 左側のカテゴリメニューから希望のカテゴリを選択できます
   - 複数のカテゴリを組み合わせてフィルタリングできます

3. **ドキュメント詳細表示**
   - ドキュメントのタイトルをクリックすると全文を表示できます
   - 関連ドキュメントとタグも一緒に表示されます

4. **ドキュメント管理（管理者）**
   - 新規ドキュメントの追加、編集、削除が可能です
   - ドキュメントにタグとカテゴリを設定できます""",

    PageType.FAQ: """FAQページの使い方：

1. **質問検索**
   - 検索バーにキーワードを入力して関連FAQを検索できます
   - よくある質問は上部に固定されています

2. **カテゴリ別閲覧**
   - カテゴリタブをクリックして分類別にFAQを確認できます
   - 各カテゴリには関連する質問がまとめられています

3. **回答の確認**
   - 質問をクリックすると回答が展開されます
   - 役に立ったかどうかフィードバックを残すことができます

4. **関連質問の確認**
   - 回答の下部で関連する他の質問を確認できます
   - 追加のヘルプが必要な場合はAIアシスタントに質問してください""",

    PageType.IMS: """IMS検索の使い方：

1. **課題検索**
   - 検索バーに自然言語で課題を検索できます
   - 例：「ログインエラー」、「パフォーマンス低下」など

2. **フィルターの使用**
   - ステータス（オープン/クローズ）、優先度、担当者でフィルタリングできます
   - 日付範囲を指定して特定期間の課題を検索できます

3. **課題詳細の表示**
   - 課題をクリックすると詳細情報を表示できます
   - 再現手順、添付ファイル、コメントを確認できます

4. **IMS連携設定**
   - 初回使用時はIMSアカウント連携が必要です
   - 設定でIMSサーバーURLと認証情報を入力してください""",

    PageType.AGENT: """AIエージェントの使い方：

1. **エージェント選択**
   - 上部のドロップダウンから適切なエージェントを選択してください
   - RAG：ドキュメントベースのQ&A
   - IMS：課題検索と分析
   - Vision：画像/チャート分析
   - Code：コード生成と分析
   - Planner：複雑なタスク計画

2. **質問する**
   - 下部の入力欄に質問を入力して送信してください
   - Shift+Enterで複数行入力が可能です

3. **ファイル添付**
   - クリップアイコンをクリックしてファイルを添付できます
   - 添付ファイルの内容に基づいて回答します

4. **会話履歴の管理**
   - 左側の履歴パネルで以前の会話を確認できます
   - 新規会話ボタンで新しいセッションを開始できます""",

    PageType.DOCUMENTS: """ドキュメント管理の使い方：

1. **ドキュメントアップロード**
   - 「アップロード」ボタンをクリックしてドキュメントを追加できます
   - PDF、DOCX、TXT、MDなど様々な形式をサポートしています
   - ドラッグ＆ドロップでもアップロードできます

2. **ドキュメント状態の確認**
   - アップロードされたドキュメントの処理状態を確認できます
   - 処理中、完了、エラーの状態が表示されます
   - チャンク数とインデックス状態も確認できます

3. **ドキュメント管理**
   - ドキュメントをフォルダ別に整理できます
   - ドキュメント削除時は関連ベクトルインデックスも一緒に削除されます

4. **検索テスト**
   - アップロードしたドキュメントで検索テストを行えます
   - AIアシスタントでドキュメントの内容について質問できます""",

    PageType.SETTINGS: """設定ページの使い方：

1. **プロフィール設定**
   - ユーザー名、メール、プロフィール写真を変更できます
   - パスワード変更もこのメニューから可能です

2. **言語とテーマ**
   - インターフェース言語を韓国語/英語/日本語から選択できます
   - ライト/ダークテーマを選択するか、システム設定に従うことができます

3. **通知設定**
   - メール通知、プッシュ通知などを設定できます
   - 通知を受け取るイベントタイプを選択できます

4. **外部連携**
   - Notion、GitHubなどの外部サービス連携を設定できます
   - APIキー管理もこのメニューから可能です""",

    PageType.ADMIN: """管理者ダッシュボードの使い方：

1. **ユーザー管理**
   - ユーザーリストでアカウントの作成、編集、削除ができます
   - ロール（管理者/一般ユーザー）と権限を設定できます

2. **システム分析**
   - 使用量統計、クエリ分析、ドキュメント状況を確認できます
   - 期間別の推移グラフでシステム使用パターンを把握できます

3. **RAG設定**
   - 検索パラメータ、チャンキング設定、モデル設定を調整できます
   - ガバナンスルールを設定して応答品質を管理できます

4. **監査ログ**
   - システムアクセス記録と変更履歴を確認できます
   - セキュリティイベントのモニタリングが可能です""",

    PageType.AI_STUDIO: """AIスタジオの使い方：

1. **Vision LLM**
   - 画像やチャートをアップロードして分析をリクエストできます
   - グラフデータの抽出、画像の説明などが可能です

2. **Sequential Pipeline**
   - 複数ステップのドキュメント処理パイプラインを構成できます
   - 抽出→分析→要約など連続タスクを自動化できます

3. **コード生成**
   - 自然言語でコード生成をリクエストできます
   - 生成されたコードはアーティファクトパネルで確認・コピーできます

4. **プロンプトテンプレート**
   - よく使うプロンプトをテンプレートとして保存できます
   - 保存したテンプレートで素早くタスクを開始できます""",

    PageType.EXTERNAL_PORTAL: """外部ポータル連携の使い方：

1. **サービス接続**
   - 「接続追加」ボタンで外部サービスを連携できます
   - Notion、GitHub、Google Drive、Confluenceをサポートしています

2. **OAuth認証**
   - 各サービスのOAuth認証を完了してください
   - 認証後、自動的にコンテンツ同期が開始されます

3. **同期管理**
   - 同期状態と最終同期時間を確認できます
   - 手動同期ボタンで即座に更新できます

4. **統合検索**
   - 連携されたすべてのソースで統合検索が可能です
   - AIアシスタントも外部ソースの情報を活用します""",

    PageType.UNKNOWN: "このページの使い方情報はありません。ヘルプが必要な場合は管理者にお問い合わせください。",
}

# Language-specific usage guide mapping
PAGE_USAGE_GUIDES_BY_LANG = {
    "ko": PAGE_USAGE_GUIDES,
    "en": PAGE_USAGE_GUIDES_EN,
    "ja": PAGE_USAGE_GUIDES_JA,
}


# Maximum content length to include in context
MAX_CONTENT_LENGTH = 2000


def filter_ui_context_by_role(
    context: UIContext,
    user_role: str
) -> FilteredUIContext:
    """
    Filter UI context based on user role.

    Admin users: See full context including content
    Regular users: See redacted content (summary only)

    Args:
        context: Full UI context from frontend
        user_role: User's role ('admin' or 'user')

    Returns:
        FilteredUIContext with appropriate content filtering
    """
    # Build selected item summary
    selected_item_summary = None
    if context.selected_item:
        selected_item_summary = {
            "type": context.selected_item.type,
            "id": context.selected_item.id,
            "title": context.selected_item.title,
        }

        # Admin sees full content, user sees truncated summary
        if user_role == "admin" and context.selected_item.content:
            selected_item_summary["content"] = context.selected_item.content[:MAX_CONTENT_LENGTH]
        elif context.selected_item.content:
            # Non-admin gets truncated preview
            content = context.selected_item.content
            selected_item_summary["content_preview"] = (
                content[:200] + "..." if len(content) > 200 else content
            )

        # Summary is always included
        if context.selected_item.summary:
            selected_item_summary["summary"] = context.selected_item.summary

        # Metadata included for all users
        if context.selected_item.metadata:
            selected_item_summary["metadata"] = context.selected_item.metadata

    return FilteredUIContext(
        current_page=context.current_page,
        page_title=context.page_title,
        selected_item_summary=selected_item_summary,
        visible_components=context.visible_components,
        language=context.language,
        theme=context.theme,
        user_permission_scope=user_role,
    )


def build_context_prompt_section(filtered_context: FilteredUIContext) -> str:
    """
    Build a context section to inject into the LLM prompt.

    This creates a human-readable description of the UI context
    that the AI can use to provide relevant responses.

    Args:
        filtered_context: Role-filtered UI context

    Returns:
        Formatted context string for prompt injection
    """
    parts = []

    # Page context with detailed description
    page_type = filtered_context.current_page
    parts.append(f"=== USER'S CURRENT SCREEN ===")
    parts.append(f"Page: {filtered_context.page_title}")

    # Add detailed page description
    if page_type in PAGE_DESCRIPTIONS:
        parts.append(f"\nPage Description:\n{PAGE_DESCRIPTIONS[page_type]}")

    # Add usage guide for the page (language-specific)
    user_lang = filtered_context.language
    usage_guides = PAGE_USAGE_GUIDES_BY_LANG.get(user_lang, PAGE_USAGE_GUIDES_EN)
    if page_type in usage_guides:
        parts.append(f"\n=== PAGE USAGE GUIDE ===\n{usage_guides[page_type]}")

    # Selected item context
    if filtered_context.selected_item_summary:
        item = filtered_context.selected_item_summary
        item_type = item.get("type", "item")
        item_title = item.get("title", "Unknown")
        parts.append(f"\n=== SELECTED ITEM ===")
        parts.append(f"Type: {item_type}")
        parts.append(f"Title: \"{item_title}\"")

        # Include content preview if available
        if "content" in item:
            content = item["content"]
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"Content:\n{content}")
        elif "content_preview" in item:
            parts.append(f"Preview: {item['content_preview']}")

    # User preferences
    lang_names = {"ko": "Korean", "en": "English", "ja": "Japanese"}
    lang = lang_names.get(filtered_context.language, filtered_context.language)
    parts.append(f"\n=== USER PREFERENCES ===")
    parts.append(f"Response Language: {lang}")
    parts.append(f"User Role: {filtered_context.user_permission_scope}")

    return "\n".join(parts)
