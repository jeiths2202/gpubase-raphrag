"""
Crawl Jobs Use Case - Orchestrates async crawling operations with progress tracking

Manages crawl job lifecycle: creation, execution, progress updates, and result storage.
"""

import asyncio
from typing import List, AsyncGenerator, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
import logging

from ...domain.entities import Issue, Attachment, CrawlJob, UserCredentials, CrawlJobStatus
from ...infrastructure.ports.crawler_port import CrawlerPort
from ...infrastructure.ports.credentials_repository_port import CredentialsRepositoryPort
from ...infrastructure.ports.issue_repository_port import IssueRepositoryPort
from ...infrastructure.ports.embedding_service_port import EmbeddingServicePort
from ...infrastructure.services.attachment_processor import AttachmentProcessor

logger = logging.getLogger(__name__)


class CrawlJobsUseCase:
    """
    Orchestrates crawl job execution with SSE progress streaming.

    Handles:
    - Job creation and lifecycle management
    - Async crawling with progress updates
    - Issue and attachment storage
    - Embedding generation for semantic search
    """

    def __init__(
        self,
        crawler: CrawlerPort,
        credentials_repository: CredentialsRepositoryPort,
        issue_repository: IssueRepositoryPort,
        embedding_service: EmbeddingServicePort,
        attachment_processor: AttachmentProcessor
    ):
        """
        Initialize crawl jobs use case.

        Args:
            crawler: Web crawler implementation
            credentials_repository: For retrieving user credentials
            issue_repository: For storing crawled issues
            embedding_service: For generating embeddings
            attachment_processor: For extracting text from attachments
        """
        self.crawler = crawler
        self.credentials_repo = credentials_repository
        self.issue_repo = issue_repository
        self.embedding = embedding_service
        self.attachment_processor = attachment_processor

        # In-memory job tracking (in production, use Redis or database)
        self._jobs: Dict[UUID, CrawlJob] = {}

    async def create_crawl_job(
        self,
        user_id: UUID,
        search_query: str,
        max_results: int = 100,
        download_attachments: bool = True,
        crawl_related: bool = False,
        max_depth: int = 1
    ) -> CrawlJob:
        """
        Create a new crawl job.

        Args:
            user_id: User ID who initiated the crawl
            search_query: IMS search query
            max_results: Maximum issues to crawl
            download_attachments: Whether to download attachments
            crawl_related: Whether to crawl related issues
            max_depth: Maximum depth for related issue crawling

        Returns:
            Created CrawlJob entity
        """
        job = CrawlJob(
            id=uuid4(),
            user_id=user_id,
            search_query=search_query,
            status=CrawlJobStatus.PENDING,
            max_results=max_results,
            download_attachments=download_attachments,
            crawl_related=crawl_related,
            max_depth=max_depth,
            created_at=datetime.utcnow(),
            started_at=None,
            completed_at=None
        )

        self._jobs[job.id] = job
        logger.info(f"Created crawl job {job.id} for user {user_id}")

        return job

    async def execute_crawl_job(
        self,
        job_id: UUID
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute crawl job with progress streaming.

        Yields progress updates as Server-Sent Events.

        Args:
            job_id: Crawl job ID

        Yields:
            Progress updates as dictionaries
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        try:
            # Update job status
            job.start()
            self._jobs[job_id] = job

            yield {
                "event": "job_started",
                "job_id": str(job.id),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Get user credentials
            credentials = await self.credentials_repo.find_by_user_id(job.user_id)
            if not credentials:
                raise ValueError(f"Credentials not found for user {job.user_id}")

            # Authenticate with IMS
            yield {
                "event": "authenticating",
                "message": "Authenticating with IMS system..."
            }

            authenticated = await self.crawler.authenticate(credentials)
            if not authenticated:
                raise Exception("Authentication failed")

            yield {
                "event": "authenticated",
                "message": "Authentication successful"
            }

            # Search for issues
            yield {
                "event": "searching",
                "message": f"Searching for issues: {job.search_query}"
            }

            issues = await self.crawler.search_issues(
                job.search_query,
                credentials,
                job.max_results
            )

            job.total_issues = len(issues)
            self._jobs[job_id] = job

            yield {
                "event": "search_completed",
                "total_issues": len(issues),
                "message": f"Found {len(issues)} issues"
            }

            # Crawl each issue
            for idx, issue in enumerate(issues, 1):
                try:
                    yield {
                        "event": "crawling_issue",
                        "issue_number": idx,
                        "total_issues": len(issues),
                        "issue_id": issue.ims_id,
                        "message": f"Crawling issue {idx}/{len(issues)}: {issue.ims_id}"
                    }

                    # Crawl full issue details
                    full_issue = await self.crawler.crawl_issue_details(issue.ims_id, credentials)

                    # Download attachments if requested
                    if job.download_attachments:
                        attachments = await self.crawler.download_attachments(full_issue, credentials)

                        # Process attachments and extract text
                        for attachment in attachments:
                            if attachment.local_path:
                                from pathlib import Path
                                extracted_text = self.attachment_processor.extract_text(
                                    Path(attachment.local_path)
                                )
                                attachment.extracted_text = extracted_text

                        full_issue.attachments = attachments

                    # Crawl related issues if requested
                    if job.crawl_related and job.max_depth > 0:
                        related_issues = await self.crawler.crawl_related_issues(
                            full_issue,
                            credentials,
                            job.max_depth
                        )
                        issues.extend(related_issues)

                        yield {
                            "event": "related_issues_found",
                            "issue_id": full_issue.ims_id,
                            "related_count": len(related_issues)
                        }

                    # Generate embedding for semantic search
                    embedding_text = f"{full_issue.title} {full_issue.description}"
                    if full_issue.attachments:
                        attachment_texts = [
                            att.extracted_text for att in full_issue.attachments
                            if att.extracted_text
                        ]
                        embedding_text += " " + " ".join(attachment_texts)

                    embedding = await self.embedding.embed_text(embedding_text)

                    # Save issue to database
                    await self.issue_repo.save(full_issue)
                    await self.issue_repo.save_embedding(full_issue.id, embedding)

                    job.crawled_issues += 1
                    self._jobs[job_id] = job

                    yield {
                        "event": "issue_completed",
                        "issue_number": idx,
                        "total_issues": len(issues),
                        "issue_id": full_issue.ims_id,
                        "crawled_count": job.crawled_issues
                    }

                except Exception as e:
                    logger.error(f"Failed to crawl issue {issue.ims_id}: {e}")
                    job.failed_issues += 1
                    self._jobs[job_id] = job

                    yield {
                        "event": "issue_failed",
                        "issue_id": issue.ims_id,
                        "error": str(e)
                    }

            # Mark job as completed
            job.complete()
            self._jobs[job_id] = job

            yield {
                "event": "job_completed",
                "job_id": str(job.id),
                "total_issues": job.total_issues,
                "crawled_issues": job.crawled_issues,
                "failed_issues": job.failed_issues,
                "timestamp": job.completed_at.isoformat() if job.completed_at else None
            }

        except Exception as e:
            logger.error(f"Crawl job {job_id} failed: {e}")
            job.fail(str(e))
            self._jobs[job_id] = job

            yield {
                "event": "job_failed",
                "job_id": str(job.id),
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

        finally:
            # Cleanup browser resources
            await self.crawler.close()

    async def get_job_status(self, job_id: UUID) -> CrawlJob:
        """
        Get current status of a crawl job.

        Args:
            job_id: Crawl job ID

        Returns:
            CrawlJob entity with current status

        Raises:
            ValueError: If job not found
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        return job

    async def cancel_job(self, job_id: UUID) -> None:
        """
        Cancel a running crawl job.

        Args:
            job_id: Crawl job ID

        Raises:
            ValueError: If job not found
        """
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if job.status == CrawlJobStatus.RUNNING:
            job.fail("Cancelled by user")
            self._jobs[job_id] = job
            logger.info(f"Cancelled crawl job {job_id}")
