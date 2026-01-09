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

            # Authenticate with IMS (check if already authenticated)
            is_already_authenticated = getattr(self.crawler, '_authenticated', False)

            if is_already_authenticated:
                # Already authenticated - skip authentication step
                yield {
                    "event": "authenticated",
                    "message": "인증 완료"
                }
            else:
                # Need to authenticate
                yield {
                    "event": "authenticating",
                    "message": "인증 중..."
                }

                authenticated = await self.crawler.authenticate(credentials)
                if not authenticated:
                    raise Exception("Authentication failed")

                yield {
                    "event": "authenticated",
                    "message": "인증 완료"
                }

            # Search for issues with progress tracking
            yield {
                "event": "searching",
                "message": f"Searching for issues: {job.raw_query}"
            }

            # Progress tracking via shared state
            search_progress = {"last_event": None, "total_pages": 0}
            crawl_progress = {"last_event": None}

            def on_search_progress(progress_data):
                search_progress["last_event"] = progress_data
                phase = progress_data.get("phase", "")
                if phase == "search_count":
                    search_progress["total_pages"] = progress_data.get("total_pages", 0)
                    print(f"[IMS Job] Found {progress_data['total_count']} issues to fetch ({progress_data['total_pages']} pages)")
                elif phase == "search_page":
                    print(f"[IMS Job] Fetching page {progress_data['current_page']}/{progress_data['total_pages']} ({progress_data['progress_percent']}%)")

            def on_crawl_progress(progress_data):
                crawl_progress["last_event"] = progress_data
                phase = progress_data.get("phase", "")
                if phase == "crawl_batch_start":
                    print(f"[IMS Job] Crawling batch {progress_data['batch_num']}/{progress_data['total_batches']} ({progress_data['progress_percent']}%)")
                elif phase == "crawl_batch_complete":
                    print(f"[IMS Job] Batch {progress_data['batch_num']} completed: {progress_data['crawled_count']}/{progress_data['total_issues']} crawled")

            # Get product_codes from job (if set during creation)
            product_codes = getattr(job, 'product_codes', None)
            issues = await self.crawler.search_issues(
                job.raw_query,
                credentials,
                product_codes=product_codes,
                progress_callback=on_search_progress
            )

            job.issues_found = len(issues)
            self._jobs[job_id] = job

            # Include search details from progress callback
            search_pages = search_progress.get("total_pages", 0)
            yield {
                "event": "search_completed",
                "total_issues": len(issues),
                "total_pages": search_pages,
                "message": f"Found {len(issues)} issues ({search_pages} pages fetched)"
            }

            # Parallel crawling: batch_size=10, sorted by ims_id descending
            BATCH_SIZE = 10
            total_issues = len(issues)
            total_batches = (total_issues + BATCH_SIZE - 1) // BATCH_SIZE if total_issues > 0 else 0

            yield {
                "event": "crawling_started",
                "total_issues": total_issues,
                "batch_size": BATCH_SIZE,
                "total_batches": total_batches,
                "message": f"Starting parallel crawl of {total_issues} issues ({total_batches} batches)"
            }

            # Crawl all issues in parallel batches (returns sorted by ims_id desc)
            crawled_issues = await self.crawler.crawl_issues_parallel(
                issues,
                credentials,
                batch_size=BATCH_SIZE,
                progress_callback=on_crawl_progress
            )

            # Yield crawl fetch completed event
            yield {
                "event": "crawl_fetch_completed",
                "fetched_count": len(crawled_issues),
                "total_issues": total_issues,
                "message": f"Fetched {len(crawled_issues)} issue details. Starting DB save and embedding generation..."
            }

            # ============================================================
            # PHASE 1: Save all issues to DB and collect embedding texts
            # ============================================================
            import time
            phase1_start = time.time()
            print(f"[IMS Crawler] Phase 1: Saving {total_issues} issues to database...")
            yield {
                "event": "phase_started",
                "phase": "saving",
                "message": f"Phase 1: Saving {total_issues} issues to database..."
            }

            # Collect data for batch embedding
            embedding_data: List[Tuple[UUID, str]] = []  # (issue_db_id, embedding_text)

            for idx, full_issue in enumerate(crawled_issues, 1):
                try:
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

                    # Save issue to database
                    saved_issue_id = await self.issue_repo.save(full_issue)
                    job.add_crawled_issue(saved_issue_id)
                    logger.debug(f"[IMS Crawler] Saved issue {full_issue.ims_id} (DB ID: {saved_issue_id})")

                    # Collect embedding text for batch processing
                    embedding_text = f"{full_issue.title} {full_issue.description}"
                    if full_issue.attachments:
                        attachment_texts = [
                            att.extracted_text for att in full_issue.attachments
                            if att.extracted_text
                        ]
                        if attachment_texts:
                            embedding_text += " " + " ".join(attachment_texts)
                    embedding_data.append((saved_issue_id, embedding_text))

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
                                saved_related_id = await self.issue_repo.save(related_issue)
                                await self.issue_repo.save_relation(
                                    source_issue_id=saved_issue_id,
                                    target_issue_id=saved_related_id,
                                    relation_type='relates_to'
                                )
                                job.related_issues_crawled += 1
                            except Exception as rel_error:
                                logger.warning(f"Failed to save relation for {related_issue.ims_id}: {rel_error}")

                    # Progress update every 10 issues
                    if idx % 10 == 0 or idx == total_issues:
                        yield {
                            "event": "saving_progress",
                            "saved_count": idx,
                            "total_issues": total_issues,
                            "message": f"Saved {idx}/{total_issues} issues to database"
                        }

                except Exception as e:
                    logger.error(f"Failed to save issue {full_issue.ims_id}: {e}")
                    yield {
                        "event": "issue_save_failed",
                        "issue_id": full_issue.ims_id,
                        "error": str(e)
                    }

            self._jobs[job_id] = job
            phase1_elapsed = time.time() - phase1_start
            print(f"[IMS Crawler] Phase 1 completed in {phase1_elapsed:.2f}s")

            # ============================================================
            # PHASE 2: Batch generate embeddings (PARALLELIZED)
            # ============================================================
            if embedding_data:
                phase2_start = time.time()
                print(f"[IMS Crawler] Phase 2: Generating embeddings for {len(embedding_data)} issues (batch processing)...")
                yield {
                    "event": "phase_started",
                    "phase": "embedding",
                    "message": f"Phase 2: Generating embeddings for {len(embedding_data)} issues (batch processing)..."
                }

                # Extract texts for batch embedding
                issue_ids = [item[0] for item in embedding_data]
                texts = [item[1] for item in embedding_data]

                try:
                    # Batch embedding - process all at once!
                    EMBEDDING_BATCH_SIZE = 32  # Process in batches to avoid memory issues
                    all_embeddings: List[List[float]] = []

                    for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                        batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(texts))
                        batch_texts = texts[batch_start:batch_end]

                        batch_embeddings = await self.embedding.embed_batch(batch_texts)
                        all_embeddings.extend(batch_embeddings)

                        yield {
                            "event": "embedding_progress",
                            "processed_count": batch_end,
                            "total_count": len(texts),
                            "message": f"Generated embeddings: {batch_end}/{len(texts)}"
                        }

                    phase2_elapsed = time.time() - phase2_start
                    print(f"[IMS Crawler] Phase 2 completed in {phase2_elapsed:.2f}s - Generated {len(all_embeddings)} embeddings")

                    # ============================================================
                    # PHASE 3: Save embeddings to DB (can be parallelized)
                    # ============================================================
                    phase3_start = time.time()
                    print(f"[IMS Crawler] Phase 3: Saving {len(all_embeddings)} embeddings to database...")
                    yield {
                        "event": "phase_started",
                        "phase": "saving_embeddings",
                        "message": f"Phase 3: Saving {len(all_embeddings)} embeddings to database..."
                    }

                    # Save embeddings in parallel batches
                    SAVE_BATCH_SIZE = 20
                    for batch_start in range(0, len(all_embeddings), SAVE_BATCH_SIZE):
                        batch_end = min(batch_start + SAVE_BATCH_SIZE, len(all_embeddings))

                        save_tasks = []
                        for i in range(batch_start, batch_end):
                            save_tasks.append(
                                self.issue_repo.save_embedding(
                                    issue_ids[i],
                                    all_embeddings[i],
                                    texts[i]
                                )
                            )

                        await asyncio.gather(*save_tasks, return_exceptions=True)

                        yield {
                            "event": "embedding_save_progress",
                            "saved_count": batch_end,
                            "total_count": len(all_embeddings),
                            "message": f"Saved embeddings: {batch_end}/{len(all_embeddings)}"
                        }

                    phase3_elapsed = time.time() - phase3_start
                    total_elapsed = time.time() - phase1_start
                    print(f"[IMS Crawler] Phase 3 completed in {phase3_elapsed:.2f}s")
                    print(f"[IMS Crawler] All phases completed in {total_elapsed:.2f}s (Phase1: DB save, Phase2: Embedding, Phase3: Embedding save)")

                except Exception as emb_error:
                    logger.error(f"Batch embedding failed: {emb_error}")
                    yield {
                        "event": "embedding_failed",
                        "error": str(emb_error),
                        "message": "Failed to generate embeddings"
                    }

            await self.crawl_job_repo.save(job)

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
