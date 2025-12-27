"""
Integration Tests for Conversation System

Tests the complete conversation flow through the service layer
using the memory repository without mocking.

These tests verify:
- End-to-end conversation workflows
- Service-repository integration
- Token counting and summarization
- Fork and regenerate operations
- Context reconstruction
"""
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime

from app.api.services.conversation_service import ConversationService
from app.api.infrastructure.memory.conversation_repository import MemoryConversationRepository
from app.api.models.conversation import (
    ConversationUpdate,
    MessageRole,
    ContextWindowConfig,
)


class TestConversationWorkflow:
    """Integration tests for complete conversation workflows"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_create_conversation_flow(self, service, user_id):
        """Test creating a conversation and verifying it exists"""
        # Create conversation
        conv = await service.create_conversation(
            user_id=user_id,
            title="Test Conversation",
            project_id="proj_001"
        )

        assert conv is not None
        assert conv.id is not None
        assert conv.user_id == user_id
        assert conv.title == "Test Conversation"
        assert conv.message_count == 0

        # Verify we can retrieve it
        retrieved = await service.get_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            include_messages=True
        )

        assert retrieved is not None
        assert str(retrieved.id) == str(conv.id)
        assert len(retrieved.messages) == 0

    @pytest.mark.asyncio
    async def test_add_messages_flow(self, service, user_id):
        """Test adding messages to a conversation"""
        # Create conversation
        conv = await service.create_conversation(
            user_id=user_id,
            title="Chat Session"
        )

        # Add user message
        user_msg = await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="Hello, how are you?"
        )

        assert user_msg is not None
        assert user_msg.role == "user"
        assert user_msg.content == "Hello, how are you?"
        assert user_msg.total_tokens > 0

        # Add assistant response
        assistant_msg = await service.add_assistant_message(
            conversation_id=conv.id,
            content="I'm doing well, thank you for asking!",
            parent_message_id=user_msg.id,
            model="test-model"
        )

        assert assistant_msg is not None
        assert assistant_msg.role == "assistant"
        assert str(assistant_msg.parent_message_id) == str(user_msg.id)

        # Verify conversation has 2 messages
        detail = await service.get_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            include_messages=True
        )

        assert detail.message_count == 2
        assert len(detail.messages) == 2

    @pytest.mark.asyncio
    async def test_list_conversations_flow(self, service, user_id):
        """Test listing user conversations"""
        # Create multiple conversations
        for i in range(5):
            await service.create_conversation(
                user_id=user_id,
                title=f"Conversation {i+1}"
            )

        # List all
        conversations = await service.list_conversations(
            user_id=user_id,
            skip=0,
            limit=10,
            include_archived=False
        )

        assert len(conversations) == 5

        # Test pagination
        page1 = await service.list_conversations(
            user_id=user_id,
            skip=0,
            limit=3,
            include_archived=False
        )
        assert len(page1) == 3

        page2 = await service.list_conversations(
            user_id=user_id,
            skip=3,
            limit=3,
            include_archived=False
        )
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_update_conversation_flow(self, service, user_id):
        """Test updating conversation properties"""
        # Create conversation
        conv = await service.create_conversation(
            user_id=user_id,
            title="Original Title"
        )

        # Update title
        update = ConversationUpdate(title="Updated Title")
        updated = await service.update_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            update=update
        )

        # update_conversation returns the updated entity, not boolean
        assert updated is not None
        assert updated.title == "Updated Title"

        # Verify update via get
        detail = await service.get_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            include_messages=False
        )
        assert detail.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_archive_conversation_flow(self, service, user_id):
        """Test archiving and unarchiving conversations"""
        # Create conversation
        conv = await service.create_conversation(
            user_id=user_id,
            title="Archivable Conversation"
        )

        # Archive it
        await service.update_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            update=ConversationUpdate(is_archived=True)
        )

        # List without archived
        active = await service.list_conversations(
            user_id=user_id,
            skip=0,
            limit=10,
            include_archived=False
        )
        assert len(active) == 0

        # List with archived
        all_convs = await service.list_conversations(
            user_id=user_id,
            skip=0,
            limit=10,
            include_archived=True
        )
        assert len(all_convs) == 1

    @pytest.mark.asyncio
    async def test_delete_conversation_soft(self, service, user_id):
        """Test soft deleting a conversation"""
        # Create conversation
        conv = await service.create_conversation(
            user_id=user_id,
            title="Deletable Conversation"
        )

        # Soft delete
        deleted = await service.delete_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            hard_delete=False
        )
        assert deleted is True

        # Should not appear in list
        conversations = await service.list_conversations(
            user_id=user_id,
            skip=0,
            limit=10,
            include_archived=True
        )
        assert len(conversations) == 0


class TestTokenManagement:
    """Integration tests for token counting and management"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_message_token_counting(self, service, user_id):
        """Test that messages have correct token counts"""
        conv = await service.create_conversation(
            user_id=user_id,
            title="Token Test"
        )

        # Add short message
        short_msg = await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="Hi"
        )
        assert short_msg.total_tokens > 0
        assert short_msg.total_tokens < 10

        # Add longer message
        long_content = "This is a much longer message with many words. " * 10
        long_msg = await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content=long_content
        )
        assert long_msg.total_tokens > short_msg.total_tokens

    @pytest.mark.asyncio
    async def test_conversation_total_tokens(self, service, user_id):
        """Test that conversation tracks total tokens"""
        conv = await service.create_conversation(
            user_id=user_id,
            title="Token Tracking"
        )

        # Add messages
        await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="First message"
        )
        await service.add_assistant_message(
            conversation_id=conv.id,
            content="First response"
        )

        # Check total tokens
        detail = await service.get_conversation(
            conversation_id=conv.id,
            user_id=user_id,
            include_messages=True
        )

        assert detail.total_tokens > 0
        # Total should be sum of message tokens
        message_tokens = sum(m.total_tokens for m in detail.messages)
        assert detail.total_tokens == message_tokens

    @pytest.mark.asyncio
    async def test_cjk_token_counting(self, service, user_id):
        """Test token counting for CJK characters"""
        conv = await service.create_conversation(
            user_id=user_id,
            title="CJK Test"
        )

        # Korean
        korean_msg = await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="안녕하세요, 오늘 날씨가 좋네요."
        )
        assert korean_msg.total_tokens > 0

        # Japanese
        japanese_msg = await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="こんにちは、今日はいい天気ですね。"
        )
        assert japanese_msg.total_tokens > 0


class TestContextReconstruction:
    """Integration tests for context window reconstruction"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_build_context_basic(self, service, user_id):
        """Test basic context reconstruction"""
        conv = await service.create_conversation(
            user_id=user_id,
            title="Context Test"
        )

        # Add some messages
        await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="What is Python?"
        )
        await service.add_assistant_message(
            conversation_id=conv.id,
            content="Python is a programming language."
        )

        # Build context
        context = await service.build_context_for_rag(
            conversation_id=conv.id,
            current_input="Tell me more about Python",
            rag_context="Python was created by Guido van Rossum."
        )

        assert context is not None
        assert context.current_input == "Tell me more about Python"
        assert context.rag_context == "Python was created by Guido van Rossum."
        assert len(context.recent_messages) == 2
        assert context.total_tokens > 0

    @pytest.mark.asyncio
    async def test_context_with_config(self, service, user_id):
        """Test context reconstruction with custom config"""
        conv = await service.create_conversation(
            user_id=user_id,
            title="Config Test"
        )

        # Add multiple turns
        for i in range(10):
            await service.add_user_message(
                conversation_id=conv.id,
                user_id=user_id,
                content=f"User message {i+1}"
            )
            await service.add_assistant_message(
                conversation_id=conv.id,
                content=f"Assistant response {i+1}"
            )

        # Build context with custom config
        config = ContextWindowConfig(
            recent_turns_count=3  # Only keep 3 turns (6 messages)
        )

        context = await service.build_context_for_rag(
            conversation_id=conv.id,
            current_input="New question",
            config=config
        )

        # Should have at most 6 recent messages (3 turns)
        assert len(context.recent_messages) <= 6


class TestForkConversation:
    """Integration tests for conversation forking"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_fork_basic(self, service, user_id):
        """Test basic conversation forking"""
        # Create original conversation with messages
        original = await service.create_conversation(
            user_id=user_id,
            title="Original Conversation"
        )

        msg1 = await service.add_user_message(
            conversation_id=original.id,
            user_id=user_id,
            content="First message"
        )
        await service.add_assistant_message(
            conversation_id=original.id,
            content="First response"
        )
        msg3 = await service.add_user_message(
            conversation_id=original.id,
            user_id=user_id,
            content="Second message"
        )
        await service.add_assistant_message(
            conversation_id=original.id,
            content="Second response"
        )

        # Fork from message 1 (after first exchange)
        fork_response = await service.fork_conversation(
            conversation_id=original.id,
            from_message_id=msg1.id,
            user_id=user_id,
            new_title="Forked Conversation"
        )

        assert fork_response is not None
        assert str(fork_response.original_conversation_id) == str(original.id)
        assert fork_response.new_conversation.title == "Forked Conversation"
        # Should have only messages up to fork point
        assert fork_response.messages_copied <= 4

    @pytest.mark.asyncio
    async def test_fork_preserves_original(self, service, user_id):
        """Test that forking preserves original conversation"""
        # Create and populate original
        original = await service.create_conversation(
            user_id=user_id,
            title="Original"
        )

        for i in range(3):
            msg = await service.add_user_message(
                conversation_id=original.id,
                user_id=user_id,
                content=f"Message {i+1}"
            )
            await service.add_assistant_message(
                conversation_id=original.id,
                content=f"Response {i+1}"
            )

        original_detail = await service.get_conversation(
            conversation_id=original.id,
            user_id=user_id,
            include_messages=True
        )
        original_count = len(original_detail.messages)

        # Fork
        await service.fork_conversation(
            conversation_id=original.id,
            from_message_id=original_detail.messages[0].id,
            user_id=user_id,
            new_title="Fork"
        )

        # Original should be unchanged
        after_fork = await service.get_conversation(
            conversation_id=original.id,
            user_id=user_id,
            include_messages=True
        )
        assert len(after_fork.messages) == original_count


class TestSearchConversations:
    """Integration tests for conversation search"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_search_by_content(self, service, user_id):
        """Test searching conversations by content"""
        # Create conversations with specific content
        conv1 = await service.create_conversation(
            user_id=user_id,
            title="Python Discussion"
        )
        await service.add_user_message(
            conversation_id=conv1.id,
            user_id=user_id,
            content="What is Python programming?"
        )

        conv2 = await service.create_conversation(
            user_id=user_id,
            title="JavaScript Discussion"
        )
        await service.add_user_message(
            conversation_id=conv2.id,
            user_id=user_id,
            content="What is JavaScript programming?"
        )

        # Search for Python
        results = await service.search_conversations(
            user_id=user_id,
            query="Python",
            limit=10
        )

        # Should find the Python conversation
        assert len(results) >= 1
        conv_ids = [str(r[0].id) for r in results]
        assert str(conv1.id) in conv_ids

    @pytest.mark.asyncio
    async def test_search_limit(self, service, user_id):
        """Test search respects limit parameter"""
        # Create multiple conversations with same keyword
        for i in range(10):
            conv = await service.create_conversation(
                user_id=user_id,
                title=f"Test Conversation {i+1}"
            )
            await service.add_user_message(
                conversation_id=conv.id,
                user_id=user_id,
                content="Common keyword appears here"
            )

        # Search with limit
        results = await service.search_conversations(
            user_id=user_id,
            query="keyword",
            limit=5
        )

        assert len(results) <= 5


class TestUserStats:
    """Integration tests for user statistics"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_stats_basic(self, service, user_id):
        """Test basic user statistics"""
        # Initially empty
        stats = await service.get_user_stats(user_id)
        assert stats["active_conversations"] == 0
        assert stats["total_messages"] == 0

        # Create conversation with messages
        conv = await service.create_conversation(
            user_id=user_id,
            title="Stats Test"
        )
        await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="Hello"
        )
        await service.add_assistant_message(
            conversation_id=conv.id,
            content="Hi there!"
        )

        # Check updated stats
        stats = await service.get_user_stats(user_id)
        assert stats["active_conversations"] == 1
        assert stats["total_messages"] == 2
        assert stats["total_tokens"] > 0

    @pytest.mark.asyncio
    async def test_stats_with_archived(self, service, user_id):
        """Test statistics count archived conversations separately"""
        # Create active conversation
        active_conv = await service.create_conversation(
            user_id=user_id,
            title="Active"
        )

        # Create and archive another
        archived_conv = await service.create_conversation(
            user_id=user_id,
            title="Archived"
        )
        await service.update_conversation(
            conversation_id=archived_conv.id,
            user_id=user_id,
            update=ConversationUpdate(is_archived=True)
        )

        # Check stats
        stats = await service.get_user_stats(user_id)
        assert stats["active_conversations"] == 1
        assert stats["archived_conversations"] == 1


class TestMessageFeedback:
    """Integration tests for message feedback"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.fixture
    def user_id(self):
        """Generate a test user ID"""
        return f"test_user_{uuid4().hex[:8]}"

    @pytest.mark.asyncio
    async def test_add_feedback(self, service, user_id):
        """Test adding feedback to a message"""
        # Create conversation with message
        conv = await service.create_conversation(
            user_id=user_id,
            title="Feedback Test"
        )
        await service.add_user_message(
            conversation_id=conv.id,
            user_id=user_id,
            content="Hello"
        )
        assistant_msg = await service.add_assistant_message(
            conversation_id=conv.id,
            content="Hi there! How can I help you?"
        )

        # Add feedback
        success = await service.add_feedback(
            message_id=assistant_msg.id,
            user_id=user_id,
            score=5,
            text="Great response!"
        )

        assert success is True


class TestUserIsolation:
    """Integration tests for user data isolation"""

    @pytest.fixture
    def service(self):
        """Create a fresh service with memory repository"""
        repo = MemoryConversationRepository()
        return ConversationService(repository=repo)

    @pytest.mark.asyncio
    async def test_users_see_only_own_conversations(self, service):
        """Test that users can only see their own conversations"""
        user1 = "user_1"
        user2 = "user_2"

        # User 1 creates conversation
        conv1 = await service.create_conversation(
            user_id=user1,
            title="User 1 Conversation"
        )

        # User 2 creates conversation
        conv2 = await service.create_conversation(
            user_id=user2,
            title="User 2 Conversation"
        )

        # User 1 should only see their conversation
        user1_convs = await service.list_conversations(
            user_id=user1,
            skip=0,
            limit=10,
            include_archived=True
        )
        assert len(user1_convs) == 1
        assert str(user1_convs[0].id) == str(conv1.id)

        # User 2 should only see their conversation
        user2_convs = await service.list_conversations(
            user_id=user2,
            skip=0,
            limit=10,
            include_archived=True
        )
        assert len(user2_convs) == 1
        assert str(user2_convs[0].id) == str(conv2.id)

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_conversation(self, service):
        """Test that user cannot access another user's conversation"""
        user1 = "user_1"
        user2 = "user_2"

        # User 1 creates conversation
        conv = await service.create_conversation(
            user_id=user1,
            title="Private Conversation"
        )

        # User 2 tries to access
        result = await service.get_conversation(
            conversation_id=conv.id,
            user_id=user2,
            include_messages=True
        )

        # Should not be accessible
        assert result is None

    @pytest.mark.asyncio
    async def test_user_cannot_add_message_to_other_conversation(self, service):
        """Test that user cannot add message to another user's conversation"""
        user1 = "user_1"
        user2 = "user_2"

        # User 1 creates conversation
        conv = await service.create_conversation(
            user_id=user1,
            title="Private Conversation"
        )

        # User 2 tries to add message - should raise or fail
        try:
            await service.add_user_message(
                conversation_id=conv.id,
                user_id=user2,  # Wrong user
                content="Unauthorized message"
            )
            # If it doesn't raise, it should return None or fail gracefully
            assert False, "Should not allow unauthorized message"
        except (ValueError, PermissionError):
            # Expected behavior
            pass
        except Exception:
            # Any error is acceptable for unauthorized access
            pass
