"""
Enhancement Service

Business logic for the AI-Driven Enhancement & Improvement Management System.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

from ..models.enhancement import (
    EnhancementStatus, EnhancementType, EnhancementPriority,
    EnhancementListItem, EnhancementDetail, CreateEnhancementRequest,
    UpdateEnhancementRequest, AttachmentInfo, TimelineEvent, TimelineEventType,
    Comment, AIAnalysisResult, ArchitectureProposal, ImplementationPlan,
    EnhancementDashboardStats
)

logger = logging.getLogger(__name__)


class EnhancementService:
    """
    Service for managing enhancement requests.

    Handles CRUD operations, status transitions, and coordination with AI agents.
    """

    def __init__(self, neo4j_client=None):
        """
        Initialize the enhancement service.

        Args:
            neo4j_client: Neo4j database client for persistence
        """
        self.neo4j = neo4j_client
        self._in_memory_store: Dict[str, Dict[str, Any]] = {}  # Fallback storage

    async def create(
        self,
        request: CreateEnhancementRequest,
        user_id: str,
        user_name: str
    ) -> EnhancementDetail:
        """
        Create a new enhancement request.

        Args:
            request: The enhancement creation request
            user_id: ID of the submitting user
            user_name: Name of the submitting user

        Returns:
            The created enhancement detail
        """
        enhancement_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create initial timeline event
        timeline_event = TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=now,
            event_type=TimelineEventType.CREATED,
            description=f"Enhancement request submitted by {user_name}",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user"
        )

        enhancement = EnhancementDetail(
            id=enhancement_id,
            title=request.title,
            description=request.description,
            type=request.type,
            priority=request.priority,
            status=EnhancementStatus.SUBMITTED,
            author_id=user_id,
            author_name=user_name,
            created_at=now,
            updated_at=now,
            ai_analyzed=False,
            attachments_count=0,
            attachments=[],
            timeline=[timeline_event],
            comments=[],
            assigned_agents=[]
        )

        # Store in Neo4j or in-memory
        await self._store_enhancement(enhancement)

        logger.info(f"Created enhancement {enhancement_id}: {request.title}")
        return enhancement

    async def get(self, enhancement_id: str) -> Optional[EnhancementDetail]:
        """
        Get an enhancement by ID.

        Args:
            enhancement_id: The enhancement ID

        Returns:
            The enhancement detail or None if not found
        """
        return await self._get_enhancement(enhancement_id)

    async def list(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[EnhancementStatus] = None,
        type_filter: Optional[EnhancementType] = None,
        priority: Optional[EnhancementPriority] = None,
        author_id: Optional[str] = None,
        search: Optional[str] = None
    ) -> Tuple[List[EnhancementListItem], int]:
        """
        List enhancements with filtering and pagination.

        Args:
            page: Page number (1-indexed)
            limit: Items per page
            status: Filter by status
            type_filter: Filter by type
            priority: Filter by priority
            author_id: Filter by author
            search: Search in title/description

        Returns:
            Tuple of (items, total_count)
        """
        items = []

        # Get all enhancements from storage
        all_enhancements = await self._list_all_enhancements()

        # Apply filters
        filtered = []
        for enh in all_enhancements:
            if status and enh.get("status") != status.value:
                continue
            if type_filter and enh.get("type") != type_filter.value:
                continue
            if priority and enh.get("priority") != priority.value:
                continue
            if author_id and enh.get("author_id") != author_id:
                continue
            if search:
                search_lower = search.lower()
                if (search_lower not in enh.get("title", "").lower() and
                    search_lower not in enh.get("description", "").lower()):
                    continue
            filtered.append(enh)

        # Sort by created_at descending
        filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Paginate
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        page_items = filtered[start:end]

        # Convert to list items
        for enh in page_items:
            items.append(EnhancementListItem(
                id=enh["id"],
                title=enh["title"],
                type=EnhancementType(enh["type"]) if enh.get("type") else None,
                priority=EnhancementPriority(enh["priority"]) if enh.get("priority") else None,
                status=EnhancementStatus(enh["status"]),
                author_id=enh["author_id"],
                author_name=enh["author_name"],
                created_at=datetime.fromisoformat(enh["created_at"]) if isinstance(enh["created_at"], str) else enh["created_at"],
                updated_at=datetime.fromisoformat(enh["updated_at"]) if isinstance(enh["updated_at"], str) else enh["updated_at"],
                ai_analyzed=enh.get("ai_analyzed", False),
                attachments_count=enh.get("attachments_count", 0)
            ))

        return items, total

    async def update(
        self,
        enhancement_id: str,
        request: UpdateEnhancementRequest,
        user_id: str,
        user_name: str
    ) -> Optional[EnhancementDetail]:
        """
        Update an enhancement.

        Args:
            enhancement_id: The enhancement ID
            request: The update request
            user_id: ID of the updating user
            user_name: Name of the updating user

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        # Update fields
        if request.title:
            enhancement.title = request.title
        if request.description:
            enhancement.description = request.description
        if request.type:
            enhancement.type = request.type
        if request.priority:
            enhancement.priority = request.priority

        enhancement.updated_at = datetime.now(timezone.utc)

        # Store updated enhancement
        await self._store_enhancement(enhancement)

        logger.info(f"Updated enhancement {enhancement_id}")
        return enhancement

    async def delete(self, enhancement_id: str, user_id: str) -> bool:
        """
        Delete an enhancement.

        Args:
            enhancement_id: The enhancement ID
            user_id: ID of the user performing deletion

        Returns:
            True if deleted, False if not found
        """
        if enhancement_id in self._in_memory_store:
            del self._in_memory_store[enhancement_id]
            logger.info(f"Deleted enhancement {enhancement_id}")
            return True
        return False

    async def update_status(
        self,
        enhancement_id: str,
        new_status: EnhancementStatus,
        actor_id: str,
        actor_name: str,
        actor_type: str = "user",
        details: Optional[Dict[str, Any]] = None
    ) -> Optional[EnhancementDetail]:
        """
        Update the status of an enhancement.

        Args:
            enhancement_id: The enhancement ID
            new_status: The new status
            actor_id: ID of the actor (user or agent)
            actor_name: Name of the actor
            actor_type: Type of actor ("user" or "agent")
            details: Optional additional details

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        old_status = enhancement.status
        enhancement.status = new_status
        enhancement.updated_at = datetime.now(timezone.utc)

        # Add timeline event
        event = TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=TimelineEventType.STATUS_CHANGED,
            description=f"Status changed from {old_status.value} to {new_status.value}",
            actor_id=actor_id,
            actor_name=actor_name,
            actor_type=actor_type,
            details=details
        )
        enhancement.timeline.append(event)

        await self._store_enhancement(enhancement)

        logger.info(f"Enhancement {enhancement_id} status: {old_status.value} -> {new_status.value}")
        return enhancement

    async def add_analysis(
        self,
        enhancement_id: str,
        analysis: AIAnalysisResult
    ) -> Optional[EnhancementDetail]:
        """
        Add AI analysis results to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            analysis: The analysis results

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        enhancement.ai_analysis = analysis
        enhancement.ai_analyzed = True
        enhancement.status = EnhancementStatus.ANALYZED
        enhancement.updated_at = datetime.now(timezone.utc)

        # Update type and priority if AI provided recommendations
        if not enhancement.type and analysis.type_classification:
            enhancement.type = analysis.type_classification
        if not enhancement.priority and analysis.priority_recommendation:
            enhancement.priority = analysis.priority_recommendation

        # Add timeline event
        event = TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=TimelineEventType.ANALYZED,
            description="AI analysis completed",
            actor_id=analysis.agent_id,
            actor_name="Analyst Agent",
            actor_type="agent",
            details={"feasibility_score": analysis.feasibility_score}
        )
        enhancement.timeline.append(event)

        await self._store_enhancement(enhancement)

        logger.info(f"Added AI analysis to enhancement {enhancement_id}")
        return enhancement

    async def add_architecture_proposal(
        self,
        enhancement_id: str,
        proposal: ArchitectureProposal,
        user_id: str = "system",
        user_name: str = "System"
    ) -> Optional[EnhancementDetail]:
        """
        Add architecture proposal to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            proposal: The architecture proposal
            user_id: ID of user who triggered the design
            user_name: Name of user who triggered the design

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        enhancement.architecture_proposal = proposal
        enhancement.updated_at = datetime.now(timezone.utc)

        # Add timeline event
        event = TimelineEvent(
            event_type="architecture_complete",
            description=f"Architecture proposal completed by {proposal.reviewer_agent_id}",
            actor_id=proposal.reviewer_agent_id,
            actor_name="Architect Agent",
            actor_type="agent",
            details={
                "approach": proposal.approach[:200] + "..." if len(proposal.approach) > 200 else proposal.approach,
                "file_changes_count": len(proposal.file_changes),
                "new_files_count": len(proposal.new_files),
                "design_decisions_count": len(proposal.design_decisions)
            }
        )
        enhancement.timeline.append(event)

        await self._store_enhancement(enhancement)

        logger.info(f"Added architecture proposal to enhancement {enhancement_id}")
        return enhancement

    async def add_timeline_event(
        self,
        enhancement_id: str,
        event: TimelineEvent
    ) -> Optional[EnhancementDetail]:
        """
        Add a timeline event to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            event: The timeline event to add

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        enhancement.timeline.append(event)
        enhancement.updated_at = datetime.now(timezone.utc)

        await self._store_enhancement(enhancement)

        logger.info(f"Added timeline event to enhancement {enhancement_id}")
        return enhancement

    async def add_implementation_plan(
        self,
        enhancement_id: str,
        plan: ImplementationPlan
    ) -> Optional[EnhancementDetail]:
        """
        Add implementation plan to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            plan: The implementation plan

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        enhancement.implementation_plan = plan
        enhancement.updated_at = datetime.now(timezone.utc)

        await self._store_enhancement(enhancement)

        logger.info(f"Added implementation plan to enhancement {enhancement_id}")
        return enhancement

    async def add_comment(
        self,
        enhancement_id: str,
        content: str,
        author_id: str,
        author_name: str,
        author_type: str = "user"
    ) -> Optional[Comment]:
        """
        Add a comment to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            content: Comment content
            author_id: Author's ID
            author_name: Author's name
            author_type: Type of author ("user" or "agent")

        Returns:
            The created comment or None if enhancement not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        comment = Comment(
            id=str(uuid.uuid4()),
            content=content,
            author_id=author_id,
            author_name=author_name,
            author_type=author_type,
            created_at=datetime.now(timezone.utc)
        )

        enhancement.comments.append(comment)
        enhancement.updated_at = datetime.now(timezone.utc)

        # Add timeline event
        event = TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=TimelineEventType.COMMENTED,
            description=f"Comment added by {author_name}",
            actor_id=author_id,
            actor_name=author_name,
            actor_type=author_type
        )
        enhancement.timeline.append(event)

        await self._store_enhancement(enhancement)

        return comment

    async def add_attachment(
        self,
        enhancement_id: str,
        attachment: AttachmentInfo,
        user_id: str,
        user_name: str
    ) -> Optional[EnhancementDetail]:
        """
        Add an attachment to an enhancement.

        Args:
            enhancement_id: The enhancement ID
            attachment: The attachment info
            user_id: Uploader's ID
            user_name: Uploader's name

        Returns:
            The updated enhancement or None if not found
        """
        enhancement = await self._get_enhancement(enhancement_id)
        if not enhancement:
            return None

        enhancement.attachments.append(attachment)
        enhancement.attachments_count = len(enhancement.attachments)
        enhancement.updated_at = datetime.now(timezone.utc)

        # Add timeline event
        event = TimelineEvent(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            event_type=TimelineEventType.ATTACHMENT_ADDED,
            description=f"Attachment '{attachment.original_name}' added",
            actor_id=user_id,
            actor_name=user_name,
            actor_type="user",
            details={"filename": attachment.original_name, "size": attachment.file_size}
        )
        enhancement.timeline.append(event)

        await self._store_enhancement(enhancement)

        return enhancement

    async def get_dashboard_stats(self) -> EnhancementDashboardStats:
        """
        Get dashboard statistics.

        Returns:
            Dashboard statistics
        """
        all_enhancements = await self._list_all_enhancements()

        stats = EnhancementDashboardStats(
            total_requests=len(all_enhancements),
            by_status={},
            by_type={},
            by_priority={},
            ai_analyzed_count=0,
            implemented_count=0
        )

        for enh in all_enhancements:
            # Count by status
            status = enh.get("status", "unknown")
            stats.by_status[status] = stats.by_status.get(status, 0) + 1

            # Count by type
            etype = enh.get("type")
            if etype:
                stats.by_type[etype] = stats.by_type.get(etype, 0) + 1

            # Count by priority
            priority = enh.get("priority")
            if priority:
                stats.by_priority[priority] = stats.by_priority.get(priority, 0) + 1

            # Count analyzed
            if enh.get("ai_analyzed"):
                stats.ai_analyzed_count += 1

            # Count implemented
            if enh.get("status") in ["verified", "released", "closed"]:
                stats.implemented_count += 1

        return stats

    # ========================================================================
    # Private storage methods
    # ========================================================================

    async def _store_enhancement(self, enhancement: EnhancementDetail) -> None:
        """Store enhancement in Neo4j or in-memory."""
        if self.neo4j:
            await self._store_in_neo4j(enhancement)
        else:
            self._in_memory_store[enhancement.id] = enhancement.model_dump(mode="json")

    async def _get_enhancement(self, enhancement_id: str) -> Optional[EnhancementDetail]:
        """Get enhancement from Neo4j or in-memory."""
        if self.neo4j:
            return await self._get_from_neo4j(enhancement_id)
        else:
            data = self._in_memory_store.get(enhancement_id)
            if data:
                return EnhancementDetail(**data)
            return None

    async def _list_all_enhancements(self) -> List[Dict[str, Any]]:
        """List all enhancements from storage."""
        if self.neo4j:
            return await self._list_from_neo4j()
        else:
            return list(self._in_memory_store.values())

    async def _store_in_neo4j(self, enhancement: EnhancementDetail) -> None:
        """Store enhancement in Neo4j."""
        query = """
        MERGE (e:EnhancementRequest {id: $id})
        SET e.title = $title,
            e.description = $description,
            e.type = $type,
            e.priority = $priority,
            e.status = $status,
            e.author_id = $author_id,
            e.author_name = $author_name,
            e.created_at = $created_at,
            e.updated_at = $updated_at,
            e.ai_analyzed = $ai_analyzed,
            e.attachments_count = $attachments_count,
            e.data = $data
        RETURN e
        """
        params = {
            "id": enhancement.id,
            "title": enhancement.title,
            "description": enhancement.description,
            "type": enhancement.type.value if enhancement.type else None,
            "priority": enhancement.priority.value if enhancement.priority else None,
            "status": enhancement.status.value,
            "author_id": enhancement.author_id,
            "author_name": enhancement.author_name,
            "created_at": enhancement.created_at.isoformat(),
            "updated_at": enhancement.updated_at.isoformat(),
            "ai_analyzed": enhancement.ai_analyzed,
            "attachments_count": enhancement.attachments_count,
            "data": enhancement.model_dump_json()
        }
        await self.neo4j.execute_query(query, params)

    async def _get_from_neo4j(self, enhancement_id: str) -> Optional[EnhancementDetail]:
        """Get enhancement from Neo4j."""
        query = """
        MATCH (e:EnhancementRequest {id: $id})
        RETURN e.data as data
        """
        result = await self.neo4j.execute_query(query, {"id": enhancement_id})
        if result and result[0]:
            import json
            data = json.loads(result[0]["data"])
            return EnhancementDetail(**data)
        return None

    async def _list_from_neo4j(self) -> List[Dict[str, Any]]:
        """List all enhancements from Neo4j."""
        query = """
        MATCH (e:EnhancementRequest)
        RETURN e.data as data
        ORDER BY e.created_at DESC
        """
        result = await self.neo4j.execute_query(query)
        import json
        return [json.loads(r["data"]) for r in result] if result else []


# Global service instance
_enhancement_service: Optional[EnhancementService] = None


def get_enhancement_service() -> EnhancementService:
    """Get the global enhancement service instance."""
    global _enhancement_service
    if _enhancement_service is None:
        _enhancement_service = EnhancementService()
    return _enhancement_service


def set_enhancement_service(service: EnhancementService) -> None:
    """Set the global enhancement service instance."""
    global _enhancement_service
    _enhancement_service = service


# ============================================================================
# Knowledge Integration Functions
# ============================================================================

async def export_enhancement_to_knowledge(enhancement: EnhancementDetail) -> Dict[str, Any]:
    """
    Export a released enhancement as knowledge content.

    Generates a structured knowledge article from the enhancement data
    that can be used for learning and similar issue resolution.

    Args:
        enhancement: The completed enhancement to export

    Returns:
        Knowledge content dictionary
    """
    # Build structured knowledge content
    content_parts = []

    # Problem description
    content_parts.append("## Problem Description")
    content_parts.append(enhancement.description)

    # AI Analysis Summary
    if enhancement.ai_analysis:
        content_parts.append("\n## AI Analysis")
        content_parts.append(f"**Summary:** {enhancement.ai_analysis.summary}")
        content_parts.append(f"**Complexity:** {enhancement.ai_analysis.estimated_complexity}")
        content_parts.append(f"**Feasibility Score:** {enhancement.ai_analysis.feasibility_score * 100:.0f}%")

        if enhancement.ai_analysis.affected_components:
            content_parts.append("\n**Affected Components:**")
            for comp in enhancement.ai_analysis.affected_components:
                content_parts.append(f"- {comp}")

    # Architecture Proposal
    if enhancement.architecture_proposal:
        content_parts.append("\n## Solution Architecture")
        content_parts.append(f"**Approach:** {enhancement.architecture_proposal.approach}")

        if enhancement.architecture_proposal.design_decisions:
            content_parts.append("\n**Key Design Decisions:**")
            for decision in enhancement.architecture_proposal.design_decisions:
                content_parts.append(f"- **{decision.title}:** {decision.description}")
                content_parts.append(f"  - Rationale: {decision.rationale}")

        if enhancement.architecture_proposal.file_changes:
            content_parts.append("\n**Files Modified:**")
            for fc in enhancement.architecture_proposal.file_changes:
                content_parts.append(f"- `{fc.file_path}` ({fc.change_type}): {fc.description}")

    # Implementation Plan
    if enhancement.implementation_plan:
        content_parts.append("\n## Implementation")

        for phase in enhancement.implementation_plan.phases:
            content_parts.append(f"\n### Phase {phase.phase_number}: {phase.title}")
            content_parts.append(phase.description)
            if phase.tasks:
                content_parts.append("\n**Tasks:**")
                for task in phase.tasks:
                    content_parts.append(f"- {task}")

        if enhancement.implementation_plan.rollback_plan:
            content_parts.append("\n**Rollback Plan:**")
            content_parts.append(enhancement.implementation_plan.rollback_plan)

    # Build the knowledge article
    knowledge_content = {
        "source_type": "enhancement",
        "source_id": enhancement.id,
        "title": f"Enhancement: {enhancement.title}",
        "content": "\n".join(content_parts),
        "summary": enhancement.ai_analysis.summary if enhancement.ai_analysis else enhancement.description[:200],
        "type": enhancement.type.value if enhancement.type else "improvement",
        "priority": enhancement.priority.value if enhancement.priority else "medium",
        "status": enhancement.status.value,
        "author_id": enhancement.author_id,
        "author_name": enhancement.author_name,
        "created_at": enhancement.created_at.isoformat(),
        "released_at": enhancement.updated_at.isoformat(),
        "tags": [],
        "metadata": {
            "complexity": enhancement.ai_analysis.estimated_complexity if enhancement.ai_analysis else None,
            "feasibility_score": enhancement.ai_analysis.feasibility_score if enhancement.ai_analysis else None,
            "affected_components": enhancement.ai_analysis.affected_components if enhancement.ai_analysis else [],
            "timeline_events": len(enhancement.timeline),
            "comments_count": len(enhancement.comments)
        }
    }

    # Add tags based on type and components
    if enhancement.type:
        knowledge_content["tags"].append(enhancement.type.value)
    if enhancement.ai_analysis and enhancement.ai_analysis.affected_components:
        knowledge_content["tags"].extend(enhancement.ai_analysis.affected_components[:5])

    return knowledge_content


async def search_similar_enhancements(
    query: str,
    service: EnhancementService,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Search for similar past enhancements.

    Uses text matching to find similar issues and their resolutions.

    Args:
        query: Search query (title or description of new enhancement)
        service: Enhancement service instance
        limit: Maximum number of results

    Returns:
        List of similar enhancements with relevance info
    """
    all_enhancements = await service._list_all_enhancements()

    # Simple text-based similarity (in production, use embedding-based search)
    query_lower = query.lower()
    query_terms = set(query_lower.split())

    scored_results = []

    for enh in all_enhancements:
        # Only include completed enhancements
        if enh.get("status") not in ["verified", "released", "closed"]:
            continue

        title = enh.get("title", "").lower()
        description = enh.get("description", "").lower()

        # Calculate simple relevance score
        title_terms = set(title.split())
        desc_terms = set(description.split())

        title_overlap = len(query_terms & title_terms)
        desc_overlap = len(query_terms & desc_terms)

        # Weight title matches higher
        score = (title_overlap * 2) + desc_overlap

        if score > 0:
            scored_results.append({
                "id": enh["id"],
                "title": enh["title"],
                "type": enh.get("type"),
                "status": enh["status"],
                "relevance_score": score,
                "summary": enh.get("description", "")[:200] + "..." if len(enh.get("description", "")) > 200 else enh.get("description", ""),
                "has_analysis": enh.get("ai_analyzed", False),
                "has_implementation": "implementation_plan" in enh and enh["implementation_plan"] is not None
            })

    # Sort by score and return top results
    scored_results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored_results[:limit]
