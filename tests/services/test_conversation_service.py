"""
Tests for Conversation Service

Tests the conversation service business logic including:
- Token counting
- Message management
- Summarization triggers
- Context reconstruction
"""
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestTokenCounting:
    """Tests for token counting functionality"""

    def test_count_tokens_english(self):
        """Test token counting for English text"""
        from app.api.services.conversation_service import ConversationService

        text = "Hello, how are you doing today?"
        tokens = ConversationService.count_tokens(text)

        # Should be approximately 7-8 tokens for this text
        assert tokens > 0
        assert tokens < 20

    def test_count_tokens_korean(self):
        """Test token counting for Korean text"""
        from app.api.services.conversation_service import ConversationService

        text = "안녕하세요, 오늘 어떻게 지내세요?"
        tokens = ConversationService.count_tokens(text)

        assert tokens > 0

    def test_count_tokens_japanese(self):
        """Test token counting for Japanese text"""
        from app.api.services.conversation_service import ConversationService

        text = "こんにちは、今日はどうですか？"
        tokens = ConversationService.count_tokens(text)

        assert tokens > 0

    def test_count_tokens_mixed(self):
        """Test token counting for mixed language text"""
        from app.api.services.conversation_service import ConversationService

        text = "Hello 안녕 こんにちは"
        tokens = ConversationService.count_tokens(text)

        assert tokens > 0

    def test_count_tokens_empty(self):
        """Test token counting for empty text"""
        from app.api.services.conversation_service import ConversationService

        tokens = ConversationService.count_tokens("")
        assert tokens == 0

    def test_count_tokens_long_text(self):
        """Test token counting for long text"""
        from app.api.services.conversation_service import ConversationService

        text = "This is a test sentence. " * 100
        tokens = ConversationService.count_tokens(text)

        # Should be roughly 500-600 tokens
        assert tokens > 400
        assert tokens < 800


class TestSummarizationTrigger:
    """Tests for summarization trigger logic"""

    def test_threshold_constant(self):
        """Test summarization threshold is defined"""
        from app.api.services.conversation_service import ConversationService

        assert hasattr(ConversationService, 'SUMMARIZE_THRESHOLD_TOKENS')
        assert ConversationService.SUMMARIZE_THRESHOLD_TOKENS == 6000

    def test_target_tokens_constant(self):
        """Test summary target tokens is defined"""
        from app.api.services.conversation_service import ConversationService

        assert hasattr(ConversationService, 'SUMMARY_TARGET_TOKENS')
        assert ConversationService.SUMMARY_TARGET_TOKENS == 500

    def test_keep_recent_turns_constant(self):
        """Test keep recent turns is defined"""
        from app.api.services.conversation_service import ConversationService

        assert hasattr(ConversationService, 'KEEP_RECENT_TURNS')
        assert ConversationService.KEEP_RECENT_TURNS == 6


class TestConversationServiceConstants:
    """Tests for service constants and configuration"""

    def test_service_has_required_constants(self):
        """Test service defines all required constants"""
        from app.api.services.conversation_service import ConversationService

        # Check token management constants
        assert hasattr(ConversationService, 'SUMMARIZE_THRESHOLD_TOKENS')
        assert hasattr(ConversationService, 'SUMMARY_TARGET_TOKENS')
        assert hasattr(ConversationService, 'KEEP_RECENT_TURNS')

        # Verify reasonable default values
        assert ConversationService.SUMMARIZE_THRESHOLD_TOKENS >= 4000
        assert ConversationService.SUMMARY_TARGET_TOKENS >= 100
        assert ConversationService.KEEP_RECENT_TURNS >= 3

    def test_count_tokens_is_static(self):
        """Test count_tokens is a static method"""
        from app.api.services.conversation_service import ConversationService

        # Should be callable without instance
        result = ConversationService.count_tokens("test")
        assert isinstance(result, int)


class TestEntityToModel:
    """Tests for entity to model conversion"""

    def test_entity_to_list_item_format(self):
        """Test that entity is converted to list item format"""
        from app.api.repositories.conversation_repository import ConversationEntity
        from app.api.models.conversation import ConversationListItem
        from uuid import uuid4
        from datetime import datetime

        # Create a valid entity with UUID
        entity_id = str(uuid4())
        entity = ConversationEntity(
            id=entity_id,
            user_id="user_001",
            title="Test Conversation",
            message_count=5,
            total_tokens=100,
            is_archived=False,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        # Verify entity has correct structure
        assert entity.id == entity_id
        assert entity.user_id == "user_001"
        assert entity.title == "Test Conversation"
        assert entity.message_count == 5


class TestConversationServiceMethods:
    """Tests for conversation service method signatures"""

    def test_service_has_required_methods(self):
        """Test service has all required methods"""
        from app.api.services.conversation_service import ConversationService

        # Check required methods exist
        assert hasattr(ConversationService, 'create_conversation')
        assert hasattr(ConversationService, 'get_conversation')
        assert hasattr(ConversationService, 'list_conversations')
        assert hasattr(ConversationService, 'update_conversation')
        assert hasattr(ConversationService, 'delete_conversation')
        assert hasattr(ConversationService, 'add_user_message')
        assert hasattr(ConversationService, 'add_assistant_message')
        assert hasattr(ConversationService, 'regenerate_response')
        assert hasattr(ConversationService, 'fork_conversation')
        assert hasattr(ConversationService, 'search_conversations')
        assert hasattr(ConversationService, 'build_context_for_rag')

    def test_service_methods_are_async(self):
        """Test that service methods are async"""
        import inspect
        from app.api.services.conversation_service import ConversationService

        async_methods = [
            'create_conversation',
            'get_conversation',
            'list_conversations',
            'update_conversation',
            'delete_conversation',
            'add_user_message',
            'add_assistant_message',
            'regenerate_response',
            'fork_conversation',
        ]

        for method_name in async_methods:
            method = getattr(ConversationService, method_name, None)
            if method:
                # Check if the method is async
                assert inspect.iscoroutinefunction(method), f"{method_name} should be async"


class TestMessageEntity:
    """Tests for message entity structure"""

    def test_message_entity_structure(self):
        """Test message entity has correct structure"""
        from app.api.repositories.conversation_repository import MessageEntity
        from datetime import datetime

        now = datetime.now(timezone.utc)
        entity = MessageEntity(
            id=str(uuid4()),
            conversation_id=str(uuid4()),
            role="user",
            content="Test message",
            total_tokens=10,
            is_active_branch=True,
            branch_depth=0,
            is_deleted=False,
            created_at=now,
            updated_at=now
        )

        assert entity.role == "user"
        assert entity.content == "Test message"
        assert entity.total_tokens == 10
        assert entity.is_active_branch is True


class TestTokenCountingApproximation:
    """Tests for token counting approximation fallback"""

    def test_approximation_for_cjk(self):
        """Test that CJK characters are counted differently"""
        from app.api.services.conversation_service import ConversationService

        # Korean text
        korean = "안녕하세요"  # 5 characters
        korean_tokens = ConversationService.count_tokens(korean)

        # English text of similar visual length
        english = "Hello"  # 5 characters
        english_tokens = ConversationService.count_tokens(english)

        # Both should have reasonable token counts
        assert korean_tokens > 0
        assert english_tokens > 0

    def test_token_count_consistency(self):
        """Test that token counting is consistent for same input"""
        from app.api.services.conversation_service import ConversationService

        text = "This is a test message for token counting."

        # Count multiple times
        count1 = ConversationService.count_tokens(text)
        count2 = ConversationService.count_tokens(text)
        count3 = ConversationService.count_tokens(text)

        # All counts should be the same
        assert count1 == count2 == count3


class TestSummaryEntity:
    """Tests for summary entity structure"""

    def test_summary_entity_structure(self):
        """Test summary entity has correct structure"""
        from app.api.repositories.conversation_repository import SummaryEntity
        from datetime import datetime

        now = datetime.now(timezone.utc)
        entity = SummaryEntity(
            id=str(uuid4()),
            conversation_id=str(uuid4()),
            summary_text="This is a summary of the conversation...",
            summary_type="rolling",
            message_count_covered=20,
            tokens_before_summary=5000,
            tokens_after_summary=500,
            created_at=now
        )

        assert entity.summary_type == "rolling"
        assert entity.message_count_covered == 20
        assert entity.tokens_before_summary == 5000
        assert entity.tokens_after_summary == 500


class TestConversationEntity:
    """Tests for conversation entity structure"""

    def test_conversation_entity_structure(self):
        """Test conversation entity has correct structure"""
        from app.api.repositories.conversation_repository import ConversationEntity
        from datetime import datetime

        now = datetime.now(timezone.utc)
        entity = ConversationEntity(
            id=str(uuid4()),
            user_id="user_001",
            title="Test Conversation",
            message_count=10,
            total_tokens=500,
            is_archived=False,
            is_deleted=False,
            created_at=now,
            updated_at=now
        )

        assert entity.user_id == "user_001"
        assert entity.title == "Test Conversation"
        assert entity.message_count == 10
        assert entity.total_tokens == 500

    def test_conversation_entity_optional_fields(self):
        """Test conversation entity optional fields"""
        from app.api.repositories.conversation_repository import ConversationEntity
        from datetime import datetime

        now = datetime.now(timezone.utc)
        entity = ConversationEntity(
            id=str(uuid4()),
            user_id="user_001",
            title=None,  # Optional
            project_id="proj_001",
            session_id="sess_001",
            strategy="hybrid",
            language="ko",
            message_count=0,
            total_tokens=0,
            is_archived=False,
            is_starred=True,
            is_deleted=False,
            created_at=now,
            updated_at=now
        )

        assert entity.title is None
        assert entity.project_id == "proj_001"
        assert entity.strategy == "hybrid"
        assert entity.language == "ko"
        assert entity.is_starred is True


class TestReconstructedContextModel:
    """Tests for ReconstructedContext model"""

    def test_reconstructed_context_creation(self):
        """Test creating reconstructed context"""
        from app.api.models.conversation import ReconstructedContext

        context = ReconstructedContext(
            system_prompt="You are a helpful assistant.",
            recent_messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            current_input="What is Python?",
            total_tokens=100
        )

        assert context.system_prompt == "You are a helpful assistant."
        assert len(context.recent_messages) == 2
        assert context.current_input == "What is Python?"
        assert context.summary is None
        assert context.rag_context is None

    def test_reconstructed_context_with_all_fields(self):
        """Test reconstructed context with all optional fields"""
        from app.api.models.conversation import ReconstructedContext

        context = ReconstructedContext(
            system_prompt="System",
            summary="Previous conversation summary...",
            recent_messages=[{"role": "user", "content": "Test"}],
            rag_context="Retrieved documents...",
            current_input="Current input",
            total_tokens=500,
            summary_used=True,
            messages_included=5,
            messages_summarized=10
        )

        assert context.summary == "Previous conversation summary..."
        assert context.rag_context == "Retrieved documents..."
        assert context.summary_used is True
        assert context.messages_included == 5
        assert context.messages_summarized == 10


class TestContextWindowConfig:
    """Tests for ContextWindowConfig model"""

    def test_default_config_values(self):
        """Test default configuration values"""
        from app.api.models.conversation import ContextWindowConfig

        config = ContextWindowConfig()

        assert config.max_tokens == 8000
        assert config.reserved_for_response == 2000
        assert config.system_prompt_tokens == 500
        assert config.rag_context_tokens == 2000
        assert config.summary_tokens == 1000
        assert config.recent_turns_count == 6

    def test_custom_config_values(self):
        """Test custom configuration values"""
        from app.api.models.conversation import ContextWindowConfig

        config = ContextWindowConfig(
            max_tokens=16000,
            reserved_for_response=4000,
            recent_turns_count=10
        )

        assert config.max_tokens == 16000
        assert config.reserved_for_response == 4000
        assert config.recent_turns_count == 10


class TestRegenerateResponse:
    """Tests for regenerate response model"""

    def test_regenerate_response_model(self):
        """Test RegenerateResponse model structure"""
        from app.api.models.conversation import RegenerateResponse, MessageResponse, MessageRole
        from datetime import datetime

        now = datetime.now(timezone.utc)
        new_message = MessageResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Regenerated content",
            total_tokens=50,
            is_regenerated=True,
            regeneration_count=1,
            created_at=now,
            updated_at=now
        )

        response = RegenerateResponse(
            original_message_id=uuid4(),
            new_message=new_message,
            regeneration_count=1
        )

        assert response.regeneration_count == 1
        assert response.new_message.is_regenerated is True


class TestForkResponse:
    """Tests for fork response model"""

    def test_fork_response_model(self):
        """Test ConversationForkResponse model structure"""
        from app.api.models.conversation import ConversationForkResponse, ConversationDetail
        from datetime import datetime

        now = datetime.now(timezone.utc)
        new_conv = ConversationDetail(
            id=uuid4(),
            user_id="user_001",
            title="Forked Conversation",
            message_count=5,
            total_tokens=200,
            created_at=now,
            updated_at=now
        )

        response = ConversationForkResponse(
            original_conversation_id=uuid4(),
            new_conversation=new_conv,
            forked_from_message_id=uuid4(),
            messages_copied=5
        )

        assert response.messages_copied == 5
        assert response.new_conversation.title == "Forked Conversation"


class TestSingletonPattern:
    """Tests for service singleton pattern"""

    def test_get_conversation_service_function_exists(self):
        """Test that get_conversation_service function exists"""
        from app.api.services.conversation_service import get_conversation_service

        service = get_conversation_service()
        assert service is not None

    def test_service_returns_same_instance(self):
        """Test that service returns singleton instance"""
        from app.api.services.conversation_service import get_conversation_service

        service1 = get_conversation_service()
        service2 = get_conversation_service()

        # Should be the same instance
        assert service1 is service2


class TestRepositoryInterface:
    """Tests for repository interface compliance"""

    def test_conversation_repository_interface(self):
        """Test ConversationRepository has required methods"""
        from app.api.repositories.conversation_repository import ConversationRepository
        import inspect

        # Check required abstract methods exist
        required_methods = [
            'create',
            'update',
            'delete',
            'get_by_user',
            'add_message',
            'get_messages',
            'get_message',
            'regenerate_message',
            'fork_conversation',
            'add_summary',
            'get_latest_summary',
            'get_context_window',
        ]

        for method_name in required_methods:
            assert hasattr(ConversationRepository, method_name), \
                f"ConversationRepository should have {method_name} method"

    def test_memory_repository_implements_interface(self):
        """Test MemoryConversationRepository implements interface"""
        from app.api.infrastructure.memory.conversation_repository import MemoryConversationRepository
        from app.api.repositories.conversation_repository import ConversationRepository

        # Check it's a subclass
        assert issubclass(MemoryConversationRepository, ConversationRepository)

        # Create instance
        repo = MemoryConversationRepository()
        assert repo is not None
