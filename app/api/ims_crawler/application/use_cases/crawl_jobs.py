"""
Crawl Jobs Use Case - Orchestrates async crawling operations with progress tracking

Manages crawl job lifecycle: creation, execution, progress updates, and result storage.
Includes DB caching to avoid re-crawling the same queries within a configurable time period.
"""

import asyncio
from typing import List, AsyncGenerator, Dict, Any, Optional, Tuple
from uuid import UUID, uuid4
from datetime import datetime
import logging

from ...domain.entities import Issue, Attachment, CrawlJob, UserCredentials, CrawlJobStatus
from ...infrastructure.ports.crawler_port import CrawlerPort
from ...infrastructure.ports.credentials_repository_port import CredentialsRepositoryPort
from ...infrastructure.ports.issue_repository_port import IssueRepositoryPort
from ...infrastructure.ports.crawl_job_repository_port import CrawlJobRepositoryPort
from ...infrastructure.ports.embedding_service_port import EmbeddingServicePort
from ...infrastructure.services.attachment_processor import AttachmentProcessor
from ....core.config import get_api_settings

logger = logging.getLogger(__name__)

# Load API settings for cache configuration
_api_settings = get_api_settings()


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
        crawl_job_repository: CrawlJobRepositoryPort,
        embedding_service: EmbeddingServicePort,
        attachment_processor: AttachmentProcessor
    ):
        """
        Initialize crawl jobs use case.

        Args:
            crawler: Web crawler implementation
            credentials_repository: For retrieving user credentials
            issue_repository: For storing crawled issues
            crawl_job_repository: For persisting crawl job state
            embedding_service: For generating embeddings
            attachment_processor: For extracting text from attachments
        """
        self.crawler = crawler
        self.credentials_repo = credentials_repository
        self.issue_repo = issue_repository
        self.crawl_job_repo = crawl_job_repository
        self.embedding = embedding_service
        self.attachment_processor = attachment_processor

        # In-memory job tracking (also persisted to database for recovery)
        self._jobs: Dict[UUID, CrawlJob] = {}

    async def create_crawl_job(
        self,
        user_id: UUID,
        search_query: str,
        max_results: int = 100,
        download_attachments: bool = True,
        crawl_related: bool = False,
        max_depth: int = 1,
        product_codes: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> Tuple[CrawlJob, bool]:
        """
        Create a new crawl job or return cached results.

        First checks if a completed crawl job with the same query exists within
        the cache period (IMS_QUERY_CACHE_HOURS). If found, returns the cached job.
        Otherwise creates a new job.

        Args:
            user_id: User ID who initiated the crawl
            search_query: IMS search query
            max_results: Maximum issues to crawl
            download_attachments: Whether to download attachments
            crawl_related: Whether to crawl related issues
            max_depth: Maximum depth for related issue crawling
            product_codes: List of product codes to filter search (e.g., ['128', '520'])
            force_refresh: If True, skip cache and always create new job

        Returns:
            Tuple of (CrawlJob entity, is_cached: bool)
            - is_cached=True means returning existing cached results
            - is_cached=False means a new job was created
        """
        cache_hours = _api_settings.IMS_QUERY_CACHE_HOURS

        # Check for cached results (unless force_refresh is True)
        if not force_refresh and cache_hours > 0:
            cached_job = await self.crawl_job_repo.find_by_query(
                user_id=user_id,
                query=search_query,
                max_age_hours=cache_hours
            )

            if cached_job:
                logger.info(
                    f"Found cached crawl job {cached_job.id} for query '{search_query}' "
                    f"(cached {cache_hours}h, created at {cached_job.created_at})"
                )
                # Store in memory cache for quick access
                self._jobs[cached_job.id] = cached_job
                return cached_job, True

        # Run cleanup of expired jobs if enabled
        if _api_settings.IMS_QUERY_CACHE_CLEANUP_ENABLED:
            try:
                deleted_count = await self.crawl_job_repo.delete_expired_jobs(cache_hours)
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired crawl jobs")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup expired jobs: {cleanup_error}")

        # Create new crawl job
        job = CrawlJob(
            id=uuid4(),
            user_id=user_id,
            raw_query=search_query,
            status=CrawlJobStatus.PENDING,
            max_issues=max_results,
            include_attachments=download_attachments,
            include_related_issues=crawl_related,
            created_at=datetime.utcnow(),
            started_at=None,
            completed_at=None
        )

        # Store product_codes for use during execution
        job.product_codes = product_codes

        self._jobs[job.id] = job

        # Persist to database
        await self.crawl_job_repo.save(job)
        logger.info(f"Created new crawl job {job.id} for user {user_id} with product_codes={product_codes}")

        return job, False

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
            await self.crawl_job_repo.save(job)  # Persist job start

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
                "message": f"Searching for issues: {job.raw_query}"
            }

            # Get product_codes from job (if set during creation)
            product_codes = getattr(job, 'product_codes', None)
            issues = await self.crawler.search_issues(
                job.raw_query,
                credentials,
                product_codes=product_codes
            )

            job.issues_found = len(issues)
            self._jobs[job_id] = job

            yield {
                "event": "search_completed",
                "total_issues": len(issues),
                "message": f"Found {len(issues)} issues"
            }

            # Parallel crawling: batch_size=10, sorted by ims_id descending
            BATCH_SIZE = 10
            total_issues = len(issues)

            yield {
                "event": "crawling_started",
                "total_issues": total_issues,
                "batch_size": BATCH_SIZE,
                "message": f"Starting parallel crawl of {total_issues} issues (batch size: {BATCH_SIZE})"
            }

            # Crawl all issues in parallel batches (returns sorted by ims_id desc)
            crawled_issues = await self.crawler.crawl_issues_parallel(
                issues,
                credentials,
                batch_size=BATCH_SIZE
            )

            # Process each crawled issue (save to DB, generate embeddings)
            for idx, full_issue in enumerate(crawled_issues, 1):
                try:
                    yield {
                        "event": "processing_issue",
                        "issue_number": idx,
                        "total_issues": total_issues,
                        "issue_id": full_issue.ims_id,
                        "message": f"Processing issue {idx}/{total_issues}: {full_issue.ims_id}"
                    }

                    # Download attachments if requested
                    if job.include_attachments:
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
                    if job.include_related_issues:
                        related_depth = 1
                        related_issues = await self.crawler.crawl_related_issues(
                            full_issue,
                            credentials,
                            related_depth
                        )

                        for related_issue in related_issues:
                            try:
                                await self.issue_repo.save(related_issue)
                                await self.issue_repo.save_relation(
                                    source_issue_id=full_issue.id,
                                    target_issue_id=related_issue.id,
                                    relation_type='relates_to'
                                )
                                job.related_issues_crawled += 1
                            except Exception as rel_error:
                                logger.warning(f"Failed to save relation for {related_issue.ims_id}: {rel_error}")

                        yield {
                            "event": "related_issues_found",
                            "issue_id": full_issue.ims_id,
                            "related_count": len(related_issues)
                        }

                    # Save issue to database
                    saved_issue_id = await self.issue_repo.save(full_issue)
                    job.add_crawled_issue(saved_issue_id)

                    # Generate and save embedding
                    try:
                        embedding_text = f"{full_issue.title} {full_issue.description}"
                        if full_issue.attachments:
                            attachment_texts = [
                                att.extracted_text for att in full_issue.attachments
                                if att.extracted_text
                            ]
                            embedding_text += " " + " ".join(attachment_texts)

                        embedding = await self.embedding.embed_text(embedding_text)
                        await self.issue_repo.save_embedding(saved_issue_id, embedding, embedding_text)
                    except Exception as emb_error:
                        logger.warning(f"Failed to save embedding for {full_issue.ims_id}: {emb_error}")

                    self._jobs[job_id] = job
                    await self.crawl_job_repo.save(job)

                    yield {
                        "event": "issue_completed",
                        "issue_number": idx,
                        "total_issues": total_issues,
                        "issue_id": full_issue.ims_id,
                        "crawled_count": job.issues_crawled
                    }

                except Exception as e:
                    logger.error(f"Failed to process issue {full_issue.ims_id}: {e}")
                    self._jobs[job_id] = job

                    yield {
                        "event": "issue_failed",
                        "issue_id": full_issue.ims_id,
                        "error": str(e)
                    }

            # Mark job as completed
            job.mark_as_completed()
            self._jobs[job_id] = job
            await self.crawl_job_repo.save(job)  # Persist completion

            yield {
                "event": "job_completed",
                "job_id": str(job.id),
                "issues_found": job.issues_found,
                "issues_crawled": job.issues_crawled,
                "attachments_processed": job.attachments_processed,
                "timestamp": job.completed_at.isoformat() if job.completed_at else None,
                "result_issue_ids": [str(iid) for iid in job.result_issue_ids]  # Include crawled issue IDs
            }

        except Exception as e:
            logger.error(f"Crawl job {job_id} failed: {e}")
            job.mark_as_failed(str(e))
            self._jobs[job_id] = job
            await self.crawl_job_repo.save(job)  # Persist failure

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
        # First check in-memory cache
        job = self._jobs.get(job_id)
        if job:
            return job

        # Fall back to database
        job = await self.crawl_job_repo.find_by_id(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Cache it for future access
        self._jobs[job_id] = job
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
            job = await self.crawl_job_repo.find_by_id(job_id)
            if not job:
                raise ValueError(f"Job {job_id} not found")

        # Check if job is in a running state (not terminal)
        if not job.is_terminal_state():
            job.mark_as_failed("Cancelled by user")
            self._jobs[job_id] = job
            await self.crawl_job_repo.save(job)  # Persist cancellation
            logger.info(f"Cancelled crawl job {job_id}")
