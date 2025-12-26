"""
Knowledge Article Service for the Knowledge Management System
Handles CRUD, workflow, translation, and recommendations
"""
import uuid
import random
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..models.knowledge_article import (
    KnowledgeArticle, KnowledgeStatus, KnowledgeCategory,
    KnowledgeTranslation, SupportedLanguage, ReviewComment,
    Recommendation, CreateKnowledgeRequest, UpdateKnowledgeRequest,
    KnowledgeSearchRequest, TopContributorResponse
)
from ..models.auth import UserRole, can_review


class EmailService:
    """Mock email service - to be implemented with actual provider"""

    @staticmethod
    async def send_email(
        to_emails: List[str],
        subject: str,
        body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        Send email to recipients.
        Currently a mock implementation.
        """
        print(f"[EMAIL MOCK] Sending to {len(to_emails)} recipients")
        print(f"[EMAIL MOCK] Subject: {subject}")
        print(f"[EMAIL MOCK] Body: {body[:100]}...")
        return True

    @staticmethod
    async def send_knowledge_notification(
        knowledge_id: str,
        knowledge_title: str,
        author_name: str,
        all_user_emails: List[str]
    ) -> bool:
        """Send knowledge registration notification to all users"""
        subject = f"[지식등록] {knowledge_title}"
        body = f"""
새로운 지식이 등록되었습니다.

제목: {knowledge_title}
작성자: {author_name}

지식 보기: /knowledge/{knowledge_id}
"""
        return await EmailService.send_email(all_user_emails, subject, body)


class TranslationService:
    """Translation service using LLM"""

    @staticmethod
    async def translate_content(
        content: str,
        source_lang: SupportedLanguage,
        target_lang: SupportedLanguage,
        is_title: bool = False
    ) -> str:
        """
        Translate content from source to target language.
        Uses LLM for high-quality translation.
        """
        # Mock translation for now - integrate with actual LLM
        if source_lang == target_lang:
            return content

        # Simple mock translations (in production, use LLM API)
        mock_suffixes = {
            SupportedLanguage.KOREAN: " (한국어)",
            SupportedLanguage.JAPANESE: " (日本語)",
            SupportedLanguage.ENGLISH: " (English)"
        }

        # In production, this would call OpenAI/Anthropic API
        # Example prompt:
        # f"Translate the following {source_lang} text to {target_lang}:\n\n{content}"

        return f"{content}{mock_suffixes.get(target_lang, '')}"

    @staticmethod
    async def generate_all_translations(
        title: str,
        content: str,
        summary: Optional[str],
        primary_language: SupportedLanguage
    ) -> Dict[str, KnowledgeTranslation]:
        """Generate translations for all supported languages"""
        translations = {}

        for lang in SupportedLanguage:
            if lang == primary_language:
                # Original language
                translations[lang.value] = KnowledgeTranslation(
                    language=lang,
                    title=title,
                    content=content,
                    summary=summary,
                    is_auto_translated=False
                )
            else:
                # Translated
                translated_title = await TranslationService.translate_content(
                    title, primary_language, lang, is_title=True
                )
                translated_content = await TranslationService.translate_content(
                    content, primary_language, lang
                )
                translated_summary = None
                if summary:
                    translated_summary = await TranslationService.translate_content(
                        summary, primary_language, lang
                    )

                translations[lang.value] = KnowledgeTranslation(
                    language=lang,
                    title=translated_title,
                    content=translated_content,
                    summary=translated_summary,
                    is_auto_translated=True
                )

        return translations


class KnowledgeArticleService:
    """Service for managing knowledge articles"""

    # In-memory storage (replace with PostgreSQL in production)
    _articles: Dict[str, KnowledgeArticle] = {}
    _recommendations: Dict[str, Recommendation] = {}
    _users: Dict[str, dict] = {
        # Mock users with roles
        "dev_user": {"id": "dev_user", "username": "developer", "role": "admin", "email": "dev@example.com", "department": "Engineering"},
        "senior_1": {"id": "senior_1", "username": "senior_dev", "role": "senior", "email": "senior@example.com", "department": "Engineering"},
        "leader_1": {"id": "leader_1", "username": "team_lead", "role": "leader", "email": "leader@example.com", "department": "Engineering"},
    }

    def __init__(self):
        self.email_service = EmailService()
        self.translation_service = TranslationService()

    async def create_article(
        self,
        request: CreateKnowledgeRequest,
        author_id: str,
        author_name: str,
        author_department: Optional[str] = None
    ) -> KnowledgeArticle:
        """Create a new knowledge article"""
        article_id = f"ka_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        article = KnowledgeArticle(
            id=article_id,
            title=request.title,
            content=request.content,
            summary=request.summary,
            primary_language=request.primary_language,
            category=request.category,
            tags=request.tags,
            author_id=author_id,
            author_name=author_name,
            author_department=author_department,
            status=KnowledgeStatus.DRAFT,
            attachments=request.attachments,
            created_at=now,
            updated_at=now
        )

        self._articles[article_id] = article
        return article

    async def get_article(self, article_id: str) -> Optional[KnowledgeArticle]:
        """Get article by ID"""
        return self._articles.get(article_id)

    async def update_article(
        self,
        article_id: str,
        request: UpdateKnowledgeRequest,
        user_id: str
    ) -> Optional[KnowledgeArticle]:
        """Update an existing article"""
        article = self._articles.get(article_id)
        if not article:
            return None

        # Only author can update (or admin)
        if article.author_id != user_id:
            return None

        # Only draft or rejected articles can be updated
        if article.status not in [KnowledgeStatus.DRAFT, KnowledgeStatus.REJECTED]:
            return None

        # Update fields
        if request.title is not None:
            article.title = request.title
        if request.content is not None:
            article.content = request.content
        if request.summary is not None:
            article.summary = request.summary
        if request.category is not None:
            article.category = request.category
        if request.tags is not None:
            article.tags = request.tags
        if request.attachments is not None:
            article.attachments = request.attachments

        article.updated_at = datetime.utcnow()
        self._articles[article_id] = article
        return article

    async def delete_article(self, article_id: str, user_id: str, user_role: str) -> bool:
        """Delete an article (author or admin only)"""
        article = self._articles.get(article_id)
        if not article:
            return False

        # Only author or admin can delete
        if article.author_id != user_id and user_role != UserRole.ADMIN:
            return False

        del self._articles[article_id]
        return True

    async def submit_for_review(
        self,
        article_id: str,
        user_id: str
    ) -> Optional[KnowledgeArticle]:
        """Submit article for review and auto-assign reviewer"""
        article = self._articles.get(article_id)
        if not article:
            return None

        if article.author_id != user_id:
            return None

        if article.status not in [KnowledgeStatus.DRAFT, KnowledgeStatus.REJECTED]:
            return None

        # Auto-assign reviewer (senior or leader, not the author)
        reviewer = await self._auto_assign_reviewer(article.author_id)

        article.status = KnowledgeStatus.PENDING
        article.submitted_at = datetime.utcnow()
        article.updated_at = datetime.utcnow()

        if reviewer:
            article.reviewer_id = reviewer["id"]
            article.reviewer_name = reviewer["username"]
            article.status = KnowledgeStatus.IN_REVIEW

        self._articles[article_id] = article

        # Send notifications
        await self._send_submission_notifications(article)

        return article

    async def _auto_assign_reviewer(self, exclude_user_id: str) -> Optional[dict]:
        """Auto-assign a reviewer (senior or leader)"""
        eligible_reviewers = [
            user for user in self._users.values()
            if user["id"] != exclude_user_id
            and user["role"] in [UserRole.SENIOR, UserRole.LEADER, UserRole.ADMIN, "senior", "leader", "admin"]
        ]

        if not eligible_reviewers:
            return None

        # Random assignment (can be improved with workload balancing)
        return random.choice(eligible_reviewers)

    async def _send_submission_notifications(self, article: KnowledgeArticle):
        """Send notifications when article is submitted"""
        # Get all user emails for broadcast
        all_emails = [u["email"] for u in self._users.values() if "email" in u]

        # Send email notification to all users
        await self.email_service.send_knowledge_notification(
            article.id,
            article.title,
            article.author_name,
            all_emails
        )

    async def review_article(
        self,
        article_id: str,
        reviewer_id: str,
        reviewer_name: str,
        action: str,  # "approve", "reject", "request_changes"
        comment: str
    ) -> Optional[KnowledgeArticle]:
        """Review an article"""
        article = self._articles.get(article_id)
        if not article:
            return None

        # Verify reviewer
        if article.reviewer_id != reviewer_id:
            return None

        if article.status != KnowledgeStatus.IN_REVIEW:
            return None

        # Add review comment
        review_comment = ReviewComment(
            id=f"rc_{uuid.uuid4().hex[:8]}",
            reviewer_id=reviewer_id,
            reviewer_name=reviewer_name,
            comment=comment,
            action=action
        )
        article.review_comments.append(review_comment)
        article.reviewed_at = datetime.utcnow()
        article.updated_at = datetime.utcnow()

        # Update status based on action
        if action == "approve":
            article.status = KnowledgeStatus.APPROVED
            # Auto-publish and generate translations
            await self._publish_article(article)
        elif action == "reject":
            article.status = KnowledgeStatus.REJECTED
        elif action == "request_changes":
            article.status = KnowledgeStatus.REJECTED  # Back to author for changes

        self._articles[article_id] = article
        return article

    async def _publish_article(self, article: KnowledgeArticle):
        """Publish article and generate translations"""
        # Generate translations for all languages
        article.translations = await self.translation_service.generate_all_translations(
            article.title,
            article.content,
            article.summary,
            article.primary_language
        )

        article.status = KnowledgeStatus.PUBLISHED
        article.published_at = datetime.utcnow()
        self._articles[article.id] = article

    async def list_articles(
        self,
        request: KnowledgeSearchRequest,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None
    ) -> tuple[List[KnowledgeArticle], int]:
        """List articles with filtering"""
        articles = []

        for article in self._articles.values():
            # Filter by status visibility
            if article.status == KnowledgeStatus.PUBLISHED:
                pass  # Everyone can see published
            elif article.status in [KnowledgeStatus.PENDING, KnowledgeStatus.IN_REVIEW]:
                # Reviewers can see pending/in_review
                if not can_review(user_role or "user"):
                    if article.author_id != user_id:
                        continue
            else:
                # Draft/Rejected only visible to author
                if article.author_id != user_id:
                    continue

            # Apply filters
            if request.query:
                query_lower = request.query.lower()
                if (query_lower not in article.title.lower() and
                    query_lower not in article.content.lower() and
                    not any(query_lower in tag.lower() for tag in article.tags)):
                    continue

            if request.category and article.category != request.category:
                continue

            if request.status and article.status != request.status:
                continue

            if request.author_id and article.author_id != request.author_id:
                continue

            if request.tags:
                if not any(tag in article.tags for tag in request.tags):
                    continue

            articles.append(article)

        # Sort by created_at descending
        articles.sort(key=lambda x: x.created_at, reverse=True)

        total = len(articles)
        start = (request.page - 1) * request.limit
        end = start + request.limit

        return articles[start:end], total

    async def list_pending_reviews(
        self,
        reviewer_id: str,
        page: int = 1,
        limit: int = 20
    ) -> tuple[List[KnowledgeArticle], int]:
        """List articles pending review for a specific reviewer"""
        articles = [
            article for article in self._articles.values()
            if article.status == KnowledgeStatus.IN_REVIEW
            and article.reviewer_id == reviewer_id
        ]

        articles.sort(key=lambda x: x.submitted_at or x.created_at)
        total = len(articles)
        start = (page - 1) * limit
        end = start + limit

        return articles[start:end], total

    async def recommend_article(
        self,
        article_id: str,
        user_id: str
    ) -> tuple[bool, int]:
        """Add recommendation to article"""
        article = self._articles.get(article_id)
        if not article:
            return False, 0

        if article.status != KnowledgeStatus.PUBLISHED:
            return False, article.recommendation_count

        # Check if already recommended
        rec_key = f"{article_id}_{user_id}"
        if rec_key in self._recommendations:
            return False, article.recommendation_count

        # Add recommendation
        self._recommendations[rec_key] = Recommendation(
            id=f"rec_{uuid.uuid4().hex[:8]}",
            knowledge_id=article_id,
            user_id=user_id
        )

        article.recommendation_count += 1
        self._articles[article_id] = article

        return True, article.recommendation_count

    async def remove_recommendation(
        self,
        article_id: str,
        user_id: str
    ) -> tuple[bool, int]:
        """Remove recommendation from article"""
        article = self._articles.get(article_id)
        if not article:
            return False, 0

        rec_key = f"{article_id}_{user_id}"
        if rec_key not in self._recommendations:
            return False, article.recommendation_count

        del self._recommendations[rec_key]
        article.recommendation_count = max(0, article.recommendation_count - 1)
        self._articles[article_id] = article

        return True, article.recommendation_count

    async def has_recommended(self, article_id: str, user_id: str) -> bool:
        """Check if user has recommended article"""
        rec_key = f"{article_id}_{user_id}"
        return rec_key in self._recommendations

    async def get_top_contributors(
        self,
        limit: int = 10,
        period: str = "all_time"
    ) -> List[TopContributorResponse]:
        """Get top contributors by recommendation count"""
        # Aggregate recommendations by author
        author_stats: Dict[str, dict] = {}

        for article in self._articles.values():
            if article.status != KnowledgeStatus.PUBLISHED:
                continue

            author_id = article.author_id
            if author_id not in author_stats:
                author_stats[author_id] = {
                    "user_id": author_id,
                    "username": article.author_name,
                    "department": article.author_department,
                    "total_recommendations": 0,
                    "article_count": 0
                }

            author_stats[author_id]["total_recommendations"] += article.recommendation_count
            author_stats[author_id]["article_count"] += 1

        # Sort by recommendations
        sorted_authors = sorted(
            author_stats.values(),
            key=lambda x: x["total_recommendations"],
            reverse=True
        )[:limit]

        return [
            TopContributorResponse(
                user_id=author["user_id"],
                username=author["username"],
                department=author["department"],
                total_recommendations=author["total_recommendations"],
                article_count=author["article_count"],
                rank=idx + 1
            )
            for idx, author in enumerate(sorted_authors)
        ]

    async def increment_view_count(self, article_id: str) -> bool:
        """Increment view count for article"""
        article = self._articles.get(article_id)
        if not article:
            return False

        article.view_count += 1
        self._articles[article_id] = article
        return True

    async def get_categories(self, language: str = "ko") -> List[dict]:
        """Get all categories with localized names"""
        from ..models.knowledge_article import CATEGORY_NAMES

        return [
            {
                "value": cat.value,
                "label": CATEGORY_NAMES.get(cat, {}).get(language, cat.value)
            }
            for cat in KnowledgeCategory
        ]


# Singleton instance
_knowledge_service: Optional[KnowledgeArticleService] = None


def get_knowledge_service() -> KnowledgeArticleService:
    """Get or create knowledge service instance"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeArticleService()
    return _knowledge_service
