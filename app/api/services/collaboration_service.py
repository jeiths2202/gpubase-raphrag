"""
Collaboration Service
Enterprise collaboration features: comments, mentions, reactions, and threads
"""
import re
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Set, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict


class CommentStatus(str, Enum):
    """Comment status"""
    ACTIVE = "active"
    RESOLVED = "resolved"
    DELETED = "deleted"


class ReactionType(str, Enum):
    """Reaction types"""
    LIKE = "like"
    LOVE = "love"
    HELPFUL = "helpful"
    CONFUSED = "confused"
    CELEBRATE = "celebrate"
    INSIGHTFUL = "insightful"


class MentionType(str, Enum):
    """Types of mentions"""
    USER = "user"
    TEAM = "team"
    EVERYONE = "everyone"


@dataclass
class Mention:
    """A mention in a comment"""
    id: str
    type: MentionType
    target_id: str  # user_id or team_id
    display_name: str
    start_index: int
    end_index: int


@dataclass
class Reaction:
    """A reaction to content"""
    id: str
    user_id: str
    user_name: str
    reaction_type: ReactionType
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["reaction_type"] = self.reaction_type.value
        return data


@dataclass
class Comment:
    """A comment on a document or knowledge item"""
    id: str
    parent_type: str  # "document", "knowledge", "answer"
    parent_id: str
    thread_id: Optional[str]  # For nested comments
    author_id: str
    author_name: str
    author_avatar: Optional[str]
    content: str
    html_content: str
    mentions: List[Mention]
    reactions: Dict[str, List[Reaction]]  # reaction_type -> reactions
    status: CommentStatus
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0
    is_pinned: bool = False
    position: Optional[Dict[str, Any]] = None  # For inline comments

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "parent_type": self.parent_type,
            "parent_id": self.parent_id,
            "thread_id": self.thread_id,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "author_avatar": self.author_avatar,
            "content": self.content,
            "html_content": self.html_content,
            "mentions": [asdict(m) for m in self.mentions],
            "reactions": {
                rt: [r.to_dict() for r in reactions]
                for rt, reactions in self.reactions.items()
            },
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reply_count": self.reply_count,
            "is_pinned": self.is_pinned,
            "position": self.position
        }
        return data


@dataclass
class CommentThread:
    """A thread of comments"""
    id: str
    parent_type: str
    parent_id: str
    root_comment_id: str
    participant_ids: Set[str]
    is_resolved: bool
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    comment_count: int
    last_activity_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "parent_type": self.parent_type,
            "parent_id": self.parent_id,
            "root_comment_id": self.root_comment_id,
            "participant_ids": list(self.participant_ids),
            "is_resolved": self.is_resolved,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "comment_count": self.comment_count,
            "last_activity_at": self.last_activity_at.isoformat()
        }


@dataclass
class MentionNotification:
    """Notification for a mention"""
    id: str
    mention_id: str
    comment_id: str
    mentioned_user_id: str
    mentioner_id: str
    mentioner_name: str
    parent_type: str
    parent_id: str
    context_preview: str
    is_read: bool
    created_at: datetime


class CollaborationService:
    """
    Collaboration features for enterprise KMS.
    Provides commenting, threading, mentions, and reactions.
    """

    # In-memory storage (use database in production)
    _comments: Dict[str, Comment] = {}
    _threads: Dict[str, CommentThread] = {}
    _comments_by_parent: Dict[str, List[str]] = defaultdict(list)
    _comments_by_thread: Dict[str, List[str]] = defaultdict(list)
    _notifications: Dict[str, List[MentionNotification]] = defaultdict(list)
    _user_subscriptions: Dict[str, Set[str]] = defaultdict(set)  # user_id -> parent_ids

    # Mention pattern: @[display_name](user:id) or @[team_name](team:id)
    MENTION_PATTERN = re.compile(r'@\[([^\]]+)\]\((\w+):([^\)]+)\)')

    def add_comment(
        self,
        parent_type: str,
        parent_id: str,
        author_id: str,
        author_name: str,
        content: str,
        thread_id: Optional[str] = None,
        author_avatar: Optional[str] = None,
        position: Optional[Dict[str, Any]] = None
    ) -> Comment:
        """
        Add a comment to a document or knowledge item.

        Args:
            parent_type: Type of parent ("document", "knowledge", "answer")
            parent_id: ID of parent item
            author_id: User ID of commenter
            author_name: Display name of commenter
            content: Comment text (may include @mentions)
            thread_id: Thread ID if this is a reply
            author_avatar: Avatar URL
            position: Position info for inline comments

        Returns:
            Created Comment
        """
        now = datetime.utcnow()

        # Parse mentions
        mentions = self._parse_mentions(content)

        # Convert to HTML (simple transformation)
        html_content = self._convert_to_html(content, mentions)

        comment = Comment(
            id=f"cmt_{uuid.uuid4().hex}",
            parent_type=parent_type,
            parent_id=parent_id,
            thread_id=thread_id,
            author_id=author_id,
            author_name=author_name,
            author_avatar=author_avatar,
            content=content,
            html_content=html_content,
            mentions=mentions,
            reactions={},
            status=CommentStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            position=position
        )

        # Store comment
        self._comments[comment.id] = comment
        self._comments_by_parent[f"{parent_type}:{parent_id}"].append(comment.id)

        # Handle threading
        if thread_id:
            self._comments_by_thread[thread_id].append(comment.id)
            if thread_id in self._threads:
                thread = self._threads[thread_id]
                thread.comment_count += 1
                thread.participant_ids.add(author_id)
                thread.last_activity_at = now

                # Update root comment reply count
                root = self._comments.get(thread.root_comment_id)
                if root:
                    root.reply_count += 1
        else:
            # Create new thread for root comment
            thread = CommentThread(
                id=f"thr_{uuid.uuid4().hex}",
                parent_type=parent_type,
                parent_id=parent_id,
                root_comment_id=comment.id,
                participant_ids={author_id},
                is_resolved=False,
                resolved_by=None,
                resolved_at=None,
                comment_count=1,
                last_activity_at=now
            )
            self._threads[thread.id] = thread
            comment.thread_id = thread.id

        # Send mention notifications
        self._create_mention_notifications(comment, mentions, author_id, author_name)

        # Subscribe author to this item
        self._user_subscriptions[author_id].add(f"{parent_type}:{parent_id}")

        return comment

    def get_comment(self, comment_id: str) -> Optional[Comment]:
        """Get a comment by ID"""
        return self._comments.get(comment_id)

    def get_comments(
        self,
        parent_type: str,
        parent_id: str,
        include_resolved: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[Comment]:
        """
        Get all comments for a parent item.

        Args:
            parent_type: Type of parent
            parent_id: ID of parent
            include_resolved: Include resolved comments
            limit: Max results
            offset: Pagination offset

        Returns:
            List of comments
        """
        key = f"{parent_type}:{parent_id}"
        comment_ids = self._comments_by_parent.get(key, [])

        comments = []
        for cid in comment_ids:
            comment = self._comments.get(cid)
            if not comment:
                continue
            if comment.status == CommentStatus.DELETED:
                continue
            if not include_resolved and comment.status == CommentStatus.RESOLVED:
                continue
            comments.append(comment)

        # Sort by created_at, pinned first
        comments.sort(key=lambda c: (not c.is_pinned, c.created_at))

        return comments[offset:offset + limit]

    def get_thread(self, thread_id: str) -> Optional[CommentThread]:
        """Get a thread by ID"""
        return self._threads.get(thread_id)

    def get_thread_comments(
        self,
        thread_id: str,
        limit: int = 100
    ) -> List[Comment]:
        """Get all comments in a thread"""
        comment_ids = self._comments_by_thread.get(thread_id, [])

        thread = self._threads.get(thread_id)
        if thread:
            # Include root comment
            comment_ids = [thread.root_comment_id] + comment_ids

        comments = []
        for cid in comment_ids:
            comment = self._comments.get(cid)
            if comment and comment.status != CommentStatus.DELETED:
                comments.append(comment)

        return comments[:limit]

    def update_comment(
        self,
        comment_id: str,
        content: str,
        editor_id: str
    ) -> Optional[Comment]:
        """
        Update a comment's content.

        Args:
            comment_id: Comment to update
            content: New content
            editor_id: User making the edit

        Returns:
            Updated Comment or None
        """
        comment = self._comments.get(comment_id)
        if not comment or comment.author_id != editor_id:
            return None

        # Re-parse mentions
        mentions = self._parse_mentions(content)
        html_content = self._convert_to_html(content, mentions)

        comment.content = content
        comment.html_content = html_content
        comment.mentions = mentions
        comment.updated_at = datetime.utcnow()

        return comment

    def delete_comment(
        self,
        comment_id: str,
        deleter_id: str,
        is_admin: bool = False
    ) -> bool:
        """Delete a comment (soft delete)"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        if comment.author_id != deleter_id and not is_admin:
            return False

        comment.status = CommentStatus.DELETED
        comment.content = "[deleted]"
        comment.html_content = "<em>[deleted]</em>"
        comment.updated_at = datetime.utcnow()

        return True

    def resolve_comment(
        self,
        comment_id: str,
        resolver_id: str
    ) -> bool:
        """Mark a comment as resolved"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        comment.status = CommentStatus.RESOLVED
        comment.updated_at = datetime.utcnow()

        # Also resolve thread if it's a root comment
        if comment.thread_id:
            thread = self._threads.get(comment.thread_id)
            if thread and thread.root_comment_id == comment_id:
                thread.is_resolved = True
                thread.resolved_by = resolver_id
                thread.resolved_at = datetime.utcnow()

        return True

    def unresolve_comment(self, comment_id: str) -> bool:
        """Unresolve a comment"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        comment.status = CommentStatus.ACTIVE
        comment.updated_at = datetime.utcnow()

        # Also unresolve thread
        if comment.thread_id:
            thread = self._threads.get(comment.thread_id)
            if thread:
                thread.is_resolved = False
                thread.resolved_by = None
                thread.resolved_at = None

        return True

    def pin_comment(self, comment_id: str) -> bool:
        """Pin a comment to the top"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        comment.is_pinned = True
        return True

    def unpin_comment(self, comment_id: str) -> bool:
        """Unpin a comment"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        comment.is_pinned = False
        return True

    def add_reaction(
        self,
        comment_id: str,
        user_id: str,
        user_name: str,
        reaction_type: ReactionType
    ) -> bool:
        """
        Add a reaction to a comment.

        Args:
            comment_id: Comment to react to
            user_id: User adding reaction
            user_name: User's display name
            reaction_type: Type of reaction

        Returns:
            Success status
        """
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        # Check if user already reacted with this type
        existing = comment.reactions.get(reaction_type.value, [])
        if any(r.user_id == user_id for r in existing):
            return False

        reaction = Reaction(
            id=f"rxn_{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            user_name=user_name,
            reaction_type=reaction_type,
            created_at=datetime.utcnow()
        )

        if reaction_type.value not in comment.reactions:
            comment.reactions[reaction_type.value] = []
        comment.reactions[reaction_type.value].append(reaction)

        return True

    def remove_reaction(
        self,
        comment_id: str,
        user_id: str,
        reaction_type: ReactionType
    ) -> bool:
        """Remove a reaction from a comment"""
        comment = self._comments.get(comment_id)
        if not comment:
            return False

        if reaction_type.value not in comment.reactions:
            return False

        original_len = len(comment.reactions[reaction_type.value])
        comment.reactions[reaction_type.value] = [
            r for r in comment.reactions[reaction_type.value]
            if r.user_id != user_id
        ]

        return len(comment.reactions[reaction_type.value]) < original_len

    def get_user_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[MentionNotification]:
        """Get mention notifications for a user"""
        notifications = self._notifications.get(user_id, [])

        if unread_only:
            notifications = [n for n in notifications if not n.is_read]

        # Sort by created_at descending
        notifications.sort(key=lambda n: n.created_at, reverse=True)

        return notifications[:limit]

    def mark_notification_read(
        self,
        notification_id: str,
        user_id: str
    ) -> bool:
        """Mark a notification as read"""
        for notif in self._notifications.get(user_id, []):
            if notif.id == notification_id:
                notif.is_read = True
                return True
        return False

    def mark_all_notifications_read(self, user_id: str) -> int:
        """Mark all notifications as read, return count"""
        count = 0
        for notif in self._notifications.get(user_id, []):
            if not notif.is_read:
                notif.is_read = True
                count += 1
        return count

    def get_comment_stats(
        self,
        parent_type: str,
        parent_id: str
    ) -> Dict[str, Any]:
        """Get commenting statistics for an item"""
        key = f"{parent_type}:{parent_id}"
        comment_ids = self._comments_by_parent.get(key, [])

        total = 0
        resolved = 0
        reactions_count = 0
        participants: Set[str] = set()

        for cid in comment_ids:
            comment = self._comments.get(cid)
            if not comment or comment.status == CommentStatus.DELETED:
                continue

            total += 1
            participants.add(comment.author_id)

            if comment.status == CommentStatus.RESOLVED:
                resolved += 1

            for rxn_list in comment.reactions.values():
                reactions_count += len(rxn_list)

        return {
            "total_comments": total,
            "resolved_comments": resolved,
            "active_comments": total - resolved,
            "total_reactions": reactions_count,
            "participant_count": len(participants),
            "participants": list(participants)
        }

    def _parse_mentions(self, content: str) -> List[Mention]:
        """Parse @mentions from content"""
        mentions = []

        for match in self.MENTION_PATTERN.finditer(content):
            display_name = match.group(1)
            mention_type_str = match.group(2)
            target_id = match.group(3)

            try:
                mention_type = MentionType(mention_type_str)
            except ValueError:
                mention_type = MentionType.USER

            mention = Mention(
                id=f"mtn_{uuid.uuid4().hex[:8]}",
                type=mention_type,
                target_id=target_id,
                display_name=display_name,
                start_index=match.start(),
                end_index=match.end()
            )
            mentions.append(mention)

        return mentions

    def _convert_to_html(self, content: str, mentions: List[Mention]) -> str:
        """Convert content with mentions to HTML"""
        html = content

        # Replace mentions with links (process in reverse to maintain indices)
        for mention in sorted(mentions, key=lambda m: m.start_index, reverse=True):
            link = f'<a href="#" class="mention mention-{mention.type.value}" data-id="{mention.target_id}">@{mention.display_name}</a>'
            html = html[:mention.start_index] + link + html[mention.end_index:]

        # Basic markdown-like conversions
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
        html = html.replace('\n', '<br>')

        return html

    def _create_mention_notifications(
        self,
        comment: Comment,
        mentions: List[Mention],
        author_id: str,
        author_name: str
    ):
        """Create notifications for mentioned users"""
        for mention in mentions:
            if mention.type != MentionType.USER:
                continue

            # Don't notify yourself
            if mention.target_id == author_id:
                continue

            notification = MentionNotification(
                id=f"ntf_{uuid.uuid4().hex}",
                mention_id=mention.id,
                comment_id=comment.id,
                mentioned_user_id=mention.target_id,
                mentioner_id=author_id,
                mentioner_name=author_name,
                parent_type=comment.parent_type,
                parent_id=comment.parent_id,
                context_preview=comment.content[:100] + ("..." if len(comment.content) > 100 else ""),
                is_read=False,
                created_at=datetime.utcnow()
            )

            self._notifications[mention.target_id].append(notification)


# Singleton instance
_collaboration_service: Optional[CollaborationService] = None


def get_collaboration_service() -> CollaborationService:
    """Get collaboration service singleton"""
    global _collaboration_service
    if _collaboration_service is None:
        _collaboration_service = CollaborationService()
    return _collaboration_service
