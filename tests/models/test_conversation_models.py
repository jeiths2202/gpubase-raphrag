"""
Tests for Conversation Models

Tests Pydantic validation for conversation-related models.
"""
import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from pydantic import ValidationError


class TestMessageRole:
    """Tests for MessageRole enum"""

    def test_all_roles_defined(self):
        """Test all expected roles are defined"""
        from app.api.models.conversation import MessageRole

        expected = ["user", "assistant", "system"]
        actual = [role.value for role in MessageRole]

        for role in expected:
            assert role in actual

    def test_role_values(self):
        """Test message role enum values"""
        from app.api.models.conversation import MessageRole

        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"


class TestMessageCreate:
    """Tests for MessageCreate model"""

    def test_valid_user_message(self):
        """Test creating valid user message"""
        from app.api.models.conversation import MessageCreate, MessageRole

        msg = MessageCreate(
            role=MessageRole.USER,
            content="Hello, how are you?"
        )

        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, how are you?"
        assert msg.parent_message_id is None

    def test_message_with_parent(self):
        """Test creating message with parent reference"""
        from app.api.models.conversation import MessageCreate, MessageRole

        parent_id = uuid4()
        msg = MessageCreate(
            role=MessageRole.ASSISTANT,
            content="I'm doing well, thank you!",
            parent_message_id=parent_id
        )

        # parent_message_id is UUID type
        assert msg.parent_message_id == parent_id
        assert isinstance(msg.parent_message_id, UUID)

    def test_empty_content_fails(self):
        """Test that empty content fails validation"""
        from app.api.models.conversation import MessageCreate, MessageRole

        with pytest.raises(ValidationError):
            MessageCreate(
                role=MessageRole.USER,
                content=""
            )

    def test_whitespace_only_content_fails(self):
        """Test that whitespace-only content fails validation"""
        from app.api.models.conversation import MessageCreate, MessageRole

        with pytest.raises(ValidationError):
            MessageCreate(
                role=MessageRole.USER,
                content="   "
            )

    def test_content_with_cjk_characters(self):
        """Test content with CJK characters"""
        from app.api.models.conversation import MessageCreate, MessageRole

        msg = MessageCreate(
            role=MessageRole.USER,
            content="こんにちは、元気ですか？"
        )

        assert "こんにちは" in msg.content


class TestConversationCreate:
    """Tests for ConversationCreate model"""

    def test_minimal_creation(self):
        """Test creating conversation with minimal fields"""
        from app.api.models.conversation import ConversationCreate

        conv = ConversationCreate()

        assert conv.title is None
        assert conv.project_id is None
        # strategy and language have defaults
        assert conv.strategy == "auto"
        assert conv.language == "auto"

    def test_full_creation(self):
        """Test creating conversation with all fields"""
        from app.api.models.conversation import ConversationCreate

        conv = ConversationCreate(
            title="My First Conversation",
            project_id="proj_123",
            strategy="hybrid",
            language="ko"
        )

        assert conv.title == "My First Conversation"
        assert conv.project_id == "proj_123"
        assert conv.strategy == "hybrid"
        assert conv.language == "ko"

    def test_title_max_length(self):
        """Test title max length validation"""
        from app.api.models.conversation import ConversationCreate

        # Should succeed with 500 chars
        long_title = "a" * 500
        conv = ConversationCreate(title=long_title)
        assert len(conv.title) == 500

        # Should fail with 501 chars
        with pytest.raises(ValidationError):
            ConversationCreate(title="a" * 501)


class TestMessageResponse:
    """Tests for MessageResponse model"""

    def test_basic_response(self):
        """Test basic message response"""
        from app.api.models.conversation import MessageResponse, MessageRole

        msg_id = uuid4()
        conv_id = uuid4()
        now = datetime.now(timezone.utc)

        response = MessageResponse(
            id=msg_id,
            conversation_id=conv_id,
            role=MessageRole.USER,
            content="Test message",
            total_tokens=10,
            created_at=now,
            updated_at=now
        )

        assert response.id == msg_id
        assert response.conversation_id == conv_id
        assert response.role == MessageRole.USER
        assert response.total_tokens == 10
        assert response.sources == []
        assert response.is_regenerated is False
        assert response.regeneration_count == 0
        assert response.is_active_branch is True

    def test_response_with_sources(self):
        """Test response with sources"""
        from app.api.models.conversation import MessageResponse, MessageRole

        sources = [
            {"document_id": "doc_1", "chunk_id": "chunk_1", "score": 0.95},
            {"document_id": "doc_2", "chunk_id": "chunk_2", "score": 0.87}
        ]
        now = datetime.now(timezone.utc)

        response = MessageResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Based on the documents...",
            total_tokens=50,
            sources=sources,
            created_at=now,
            updated_at=now
        )

        assert len(response.sources) == 2
        assert response.sources[0]["score"] == 0.95

    def test_regenerated_message(self):
        """Test regenerated message response"""
        from app.api.models.conversation import MessageResponse, MessageRole

        now = datetime.now(timezone.utc)

        response = MessageResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="Regenerated response",
            total_tokens=30,
            is_regenerated=True,
            regeneration_count=2,
            created_at=now,
            updated_at=now
        )

        assert response.is_regenerated is True
        assert response.regeneration_count == 2


class TestConversationListItem:
    """Tests for ConversationListItem model"""

    def test_basic_list_item(self):
        """Test basic conversation list item"""
        from app.api.models.conversation import ConversationListItem

        conv_id = uuid4()
        now = datetime.now(timezone.utc)

        item = ConversationListItem(
            id=conv_id,
            title="Test Conversation",
            message_count=10,
            total_tokens=1500,
            created_at=now,
            updated_at=now
        )

        assert item.id == conv_id
        assert item.message_count == 10
        assert item.total_tokens == 1500
        assert item.is_archived is False

    def test_archived_item(self):
        """Test archived conversation list item"""
        from app.api.models.conversation import ConversationListItem

        now = datetime.now(timezone.utc)
        item = ConversationListItem(
            id=uuid4(),
            title="Archived Conversation",
            message_count=50,
            total_tokens=8000,
            is_archived=True,
            created_at=now,
            updated_at=now
        )

        assert item.is_archived is True


class TestConversationDetail:
    """Tests for ConversationDetail model"""

    def test_detail_with_messages(self):
        """Test conversation detail with messages"""
        from app.api.models.conversation import ConversationDetail, MessageResponse, MessageRole

        conv_id = uuid4()
        now = datetime.now(timezone.utc)

        messages = [
            MessageResponse(
                id=uuid4(),
                conversation_id=conv_id,
                role=MessageRole.USER,
                content="Hello",
                total_tokens=5,
                created_at=now,
                updated_at=now
            ),
            MessageResponse(
                id=uuid4(),
                conversation_id=conv_id,
                role=MessageRole.ASSISTANT,
                content="Hi there!",
                total_tokens=10,
                created_at=now,
                updated_at=now
            )
        ]

        detail = ConversationDetail(
            id=conv_id,
            user_id="user_001",
            title="Chat with AI",
            message_count=2,
            total_tokens=15,
            messages=messages,
            created_at=now,
            updated_at=now
        )

        assert len(detail.messages) == 2
        assert detail.message_count == 2
        assert detail.active_summary is None
        assert detail.user_id == "user_001"

    def test_detail_with_summary(self):
        """Test conversation detail with active summary"""
        from app.api.models.conversation import ConversationDetail

        now = datetime.now(timezone.utc)
        detail = ConversationDetail(
            id=uuid4(),
            user_id="user_001",
            title="Long Conversation",
            message_count=100,
            total_tokens=15000,
            active_summary="This conversation covered topics about...",
            created_at=now,
            updated_at=now
        )

        assert detail.active_summary is not None
        assert "conversation" in detail.active_summary.lower()


class TestRegenerateRequest:
    """Tests for RegenerateRequest model"""

    def test_basic_regenerate(self):
        """Test basic regenerate request"""
        from app.api.models.conversation import RegenerateRequest

        msg_id = uuid4()
        request = RegenerateRequest(message_id=msg_id)

        # message_id is UUID type
        assert request.message_id == msg_id
        assert isinstance(request.message_id, UUID)
        assert request.strategy is None

    def test_regenerate_with_strategy(self):
        """Test regenerate request with different strategy"""
        from app.api.models.conversation import RegenerateRequest

        request = RegenerateRequest(
            message_id=uuid4(),
            strategy="graph"
        )

        assert request.strategy == "graph"


class TestConversationForkRequest:
    """Tests for ConversationForkRequest model"""

    def test_basic_fork(self):
        """Test basic fork request"""
        from app.api.models.conversation import ConversationForkRequest

        msg_id = uuid4()
        request = ConversationForkRequest(from_message_id=msg_id)

        assert request.from_message_id == msg_id
        assert isinstance(request.from_message_id, UUID)
        assert request.new_title is None

    def test_fork_with_title(self):
        """Test fork request with custom title"""
        from app.api.models.conversation import ConversationForkRequest

        request = ConversationForkRequest(
            from_message_id=uuid4(),
            new_title="Forked: Exploring alternative approach"
        )

        assert "Forked" in request.new_title


class TestReconstructedContext:
    """Tests for ReconstructedContext model"""

    def test_basic_context(self):
        """Test basic reconstructed context"""
        from app.api.models.conversation import ReconstructedContext

        context = ReconstructedContext(
            system_prompt="You are a helpful assistant",
            recent_messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"}
            ],
            current_input="What is Python?",
            total_tokens=100
        )

        assert len(context.recent_messages) == 2
        assert context.summary is None
        assert context.rag_context is None
        assert context.total_tokens == 100

    def test_full_context(self):
        """Test full reconstructed context with all fields"""
        from app.api.models.conversation import ReconstructedContext

        context = ReconstructedContext(
            system_prompt="You are a helpful assistant",
            summary="Previous discussion about machine learning...",
            recent_messages=[
                {"role": "user", "content": "Continue our discussion"}
            ],
            rag_context="Retrieved: Python is a programming language...",
            current_input="Tell me more about Python",
            total_tokens=500
        )

        assert context.summary is not None
        assert context.rag_context is not None
        assert "Python" in context.rag_context


class TestContextWindowConfig:
    """Tests for ContextWindowConfig model"""

    def test_default_config(self):
        """Test default context window configuration"""
        from app.api.models.conversation import ContextWindowConfig

        config = ContextWindowConfig()

        assert config.max_tokens == 8000
        assert config.reserved_for_response == 2000
        assert config.system_prompt_tokens == 500
        assert config.rag_context_tokens == 2000

    def test_custom_config(self):
        """Test custom context window configuration"""
        from app.api.models.conversation import ContextWindowConfig

        config = ContextWindowConfig(
            max_tokens=16000,
            reserved_for_response=4000
        )

        assert config.max_tokens == 16000
        assert config.reserved_for_response == 4000


class TestMessageFeedback:
    """Tests for MessageFeedback model"""

    def test_valid_feedback(self):
        """Test valid feedback scores"""
        from app.api.models.conversation import MessageFeedback

        for score in [1, 2, 3, 4, 5]:
            feedback = MessageFeedback(score=score)
            assert feedback.score == score

    def test_invalid_feedback_too_low(self):
        """Test feedback score below minimum"""
        from app.api.models.conversation import MessageFeedback

        with pytest.raises(ValidationError):
            MessageFeedback(score=0)

    def test_invalid_feedback_too_high(self):
        """Test feedback score above maximum"""
        from app.api.models.conversation import MessageFeedback

        with pytest.raises(ValidationError):
            MessageFeedback(score=6)

    def test_feedback_with_text(self):
        """Test feedback with optional text"""
        from app.api.models.conversation import MessageFeedback

        feedback = MessageFeedback(score=5, text="Great response!")
        assert feedback.text == "Great response!"


class TestConversationUpdate:
    """Tests for ConversationUpdate model"""

    def test_partial_update(self):
        """Test partial conversation update"""
        from app.api.models.conversation import ConversationUpdate

        update = ConversationUpdate(title="New Title")

        assert update.title == "New Title"
        assert update.is_archived is None
        assert update.strategy is None

    def test_archive_update(self):
        """Test archiving conversation"""
        from app.api.models.conversation import ConversationUpdate

        update = ConversationUpdate(is_archived=True)

        assert update.is_archived is True
        assert update.title is None

    def test_full_update(self):
        """Test full conversation update"""
        from app.api.models.conversation import ConversationUpdate

        update = ConversationUpdate(
            title="Updated Title",
            is_archived=False,
            strategy="vector",
            language="ja"
        )

        assert update.title == "Updated Title"
        assert update.is_archived is False
        assert update.strategy == "vector"
        assert update.language == "ja"


class TestSummaryType:
    """Tests for SummaryType enum"""

    def test_summary_types(self):
        """Test all summary types are defined"""
        from app.api.models.conversation import SummaryType

        assert SummaryType.ROLLING.value == "rolling"
        assert SummaryType.CHECKPOINT.value == "checkpoint"
        assert SummaryType.FINAL.value == "final"


class TestSummaryResponse:
    """Tests for SummaryResponse model"""

    def test_basic_summary(self):
        """Test basic summary response"""
        from app.api.models.conversation import SummaryResponse, SummaryType

        now = datetime.now(timezone.utc)
        summary = SummaryResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            summary_text="This conversation discussed Python programming...",
            summary_type=SummaryType.ROLLING,
            message_count_covered=20,
            tokens_before_summary=5000,
            tokens_after_summary=500,
            created_at=now
        )

        assert summary.summary_type == SummaryType.ROLLING
        assert summary.message_count_covered == 20
        assert summary.tokens_before_summary == 5000

    def test_summary_with_topics(self):
        """Test summary with key topics"""
        from app.api.models.conversation import SummaryResponse, SummaryType

        summary = SummaryResponse(
            id=uuid4(),
            conversation_id=uuid4(),
            summary_text="Summary...",
            summary_type=SummaryType.CHECKPOINT,
            message_count_covered=10,
            tokens_before_summary=2000,
            tokens_after_summary=200,
            key_topics=["Python", "Machine Learning", "AI"],
            created_at=datetime.now(timezone.utc)
        )

        assert len(summary.key_topics) == 3
        assert "Python" in summary.key_topics
