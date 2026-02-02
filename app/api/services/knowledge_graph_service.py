"""
Knowledge Graph Service
지식 그래프 생성, 관리 및 쿼리 서비스

Based on Neo4j Knowledge Graph patterns:
- Entity extraction using NLP/LLM
- Relationship inference
- Ontology-based schema
- Cypher query generation
"""
import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import defaultdict

from ..models.knowledge_graph import (
    EntityType,
    RelationType,
    KGEntity,
    KGRelationship,
    KnowledgeGraph,
    KGSummary,
    Ontology,
    OntologyClass,
    OntologyRelation,
)


class EntityExtractor:
    """
    Entity extraction from text using NLP patterns and LLM.

    In production, this would use:
    - spaCy NER
    - Hugging Face transformers
    - LLM-based extraction (GPT-4, Claude)
    """

    # Entity patterns for rule-based extraction
    ENTITY_PATTERNS = {
        EntityType.PERSON: [
            r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',  # Western names
            r'\b[가-힣]{2,4}\s*(?:씨|님|교수|박사|대표|사장)\b',  # Korean names with titles
        ],
        EntityType.ORGANIZATION: [
            r'\b[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)* (?:Inc|Corp|LLC|Ltd|Company|그룹|주식회사|㈜)\b',
            r'\b(?:Google|Microsoft|Amazon|Apple|Meta|OpenAI|Anthropic|NVIDIA)\b',
            r'\b[가-힣]+(?:회사|기업|그룹|연구소|대학교|병원)\b',
        ],
        EntityType.TECHNOLOGY: [
            r'\b(?:Python|Java|JavaScript|TypeScript|Rust|Go|C\+\+|React|Vue|Angular)\b',
            r'\b(?:Neo4j|PostgreSQL|MongoDB|Redis|Elasticsearch|Kubernetes|Docker)\b',
            r'\b(?:GPT-4|Claude|LLaMA|BERT|Transformer|RAG|LLM|NLP|ML|AI)\b',
        ],
        EntityType.LOCATION: [
            r'\b(?:Seoul|Tokyo|New York|London|Paris|Berlin|서울|도쿄|뉴욕|런던|파리)\b',
            r'\b[가-힣]+(?:시|도|구|동|읍|면|리)\b',
        ],
        EntityType.DATE: [
            r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',
            r'\b\d{4}년\s*\d{1,2}월\s*\d{1,2}일\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        ],
        EntityType.QUANTITY: [
            r'\b\d+(?:\.\d+)?(?:\s*(?:percent|%|달러|원|억|만|천|백|십|개|명|건))\b',
            r'\b(?:\$|₩|€|£)\s*\d+(?:,\d{3})*(?:\.\d+)?\b',
        ],
        # OpenFrame/Mainframe command patterns
        EntityType.COMMAND: [
            # OpenFrame *mgr commands (tjesmgr, hidbmgr, ofmgr, etc.)
            r'\b(?:tjes|hidb|of|tac|tso|vtam|cics|batch|online)mgr\b',
            # OpenFrame management commands
            r'\b(?:tjesmgr|hidbmgr|ofmgr|tacfmgr|tsomgr|vtammgr|cicsmgr)\s+[A-Z]+\b',
            # Common mainframe utilities
            r'\b(?:IDCAMS|IEBGENER|IEBCOPY|IEFBR14|SORT|DFSORT)\b',
            # JCL keywords
            r'\b(?:DD|DSN|DISP|SPACE|DCB|VOL|UNIT|SYSOUT|COND)\b',
        ],
        # Error code patterns
        EntityType.ERROR_CODE: [
            # Numeric error codes with dash prefix (-5212, -17201), also handles (-5212)
            r'(?<![A-Z])-\d{4,5}(?![0-9])',
            # Product-specific error codes (JEUS-1234, ORA-12154, TIBERO-5001)
            r'\b(?:JEUS|TIBERO|TMAX|OFM|OFCOBOL|OFASM|ORA|SQL|ERR|ERROR)-\d{4,5}\b',
            # Named error constants (DSALC_ERR_*, BASE_ERR_*)
            r'\b(?:DSALC|BASE|AIM|TJES|HIDB|TACF)_(?:ERR|ERROR)_[A-Z_]+\b',
        ],
        # Configuration file/parameter patterns
        EntityType.CONFIG: [
            # OpenFrame config files
            r'\b(?:oframe|tjes|hidb|osc|tacf)\.conf\b',
            # Configuration sections [SECTION_NAME]
            r'\[\s*[A-Z_]+\s*\]',
            # Environment variables
            r'\b(?:OPENFRAME_HOME|TMAX_HOST_ADDR|TB_SID|COBDIR)\b',
        ],
    }

    # Korean entity patterns
    KOREAN_PATTERNS = {
        EntityType.CONCEPT: [
            r'[가-힣]+(?:기술|시스템|방법|모델|알고리즘|프레임워크|아키텍처)',
            r'[가-힣]+(?:분석|처리|추출|생성|검색|학습)',
        ],
        EntityType.TERM: [
            r'[가-힣]+(?:이란|이라는|이라고|이라 함)',
        ],
    }

    async def extract_entities(
        self,
        text: str,
        entity_types: List[EntityType] = None,
        language: str = "auto",
        use_llm: bool = True
    ) -> List[KGEntity]:
        """
        Extract entities from text.

        Args:
            text: Input text
            entity_types: Types to extract (None = all)
            language: Text language
            use_llm: Use LLM for extraction

        Returns:
            List of extracted entities
        """
        entities = []
        seen_labels = set()

        # Detect language if auto
        if language == "auto":
            language = self._detect_language(text)

        # Rule-based extraction
        types_to_extract = entity_types or list(EntityType)

        for entity_type in types_to_extract:
            patterns = self.ENTITY_PATTERNS.get(entity_type, [])
            if language == "ko":
                patterns.extend(self.KOREAN_PATTERNS.get(entity_type, []))

            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    label = match.strip()
                    if label and label.lower() not in seen_labels:
                        seen_labels.add(label.lower())
                        entities.append(KGEntity(
                            id=f"ent_{uuid.uuid4().hex[:8]}",
                            label=label,
                            entity_type=entity_type,
                            confidence=0.7,  # Rule-based confidence
                            properties={"extraction_method": "pattern"}
                        ))

        # LLM-based extraction for better quality
        if use_llm:
            llm_entities = await self._extract_with_llm(text, language)
            for ent in llm_entities:
                if ent.label.lower() not in seen_labels:
                    seen_labels.add(ent.label.lower())
                    entities.append(ent)

        return entities

    async def _extract_with_llm(
        self,
        text: str,
        language: str
    ) -> List[KGEntity]:
        """
        Extract entities using LLM.

        In production, this would call actual LLM API.
        """
        await asyncio.sleep(0.3)  # Simulate LLM call

        # Mock LLM extraction based on text content
        entities = []

        # Extract key concepts from text
        words = text.split()
        important_words = []

        for i, word in enumerate(words):
            # Look for capitalized words or Korean compound words
            if len(word) > 2:
                if word[0].isupper() or (
                    any('\uac00' <= c <= '\ud7a3' for c in word) and len(word) >= 2
                ):
                    important_words.append(word)

        # Create entities from important words
        for word in important_words[:10]:  # Limit to 10
            entity_type = self._infer_entity_type(word)
            entities.append(KGEntity(
                id=f"ent_{uuid.uuid4().hex[:8]}",
                label=word,
                entity_type=entity_type,
                confidence=0.85,
                properties={"extraction_method": "llm"}
            ))

        return entities

    def _detect_language(self, text: str) -> str:
        """Detect text language."""
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3')
        total_chars = len(text.replace(' ', ''))
        if total_chars > 0 and korean_chars / total_chars > 0.3:
            return "ko"
        return "en"

    def _infer_entity_type(self, text: str) -> EntityType:
        """Infer entity type from text."""
        text_lower = text.lower()

        # Technology indicators
        tech_keywords = ['ai', 'ml', 'api', 'sdk', 'db', 'sql', 'graph', 'cloud', 'rag', 'llm']
        if any(kw in text_lower for kw in tech_keywords):
            return EntityType.TECHNOLOGY

        # Organization indicators
        org_keywords = ['inc', 'corp', 'ltd', '회사', '기업', '연구소']
        if any(kw in text_lower for kw in org_keywords):
            return EntityType.ORGANIZATION

        # Default to concept
        return EntityType.CONCEPT

    # =========================================================================
    # M1: Entity Confidence Filtering
    # =========================================================================

    def filter_by_confidence(
        self,
        entities: List[KGEntity],
        threshold: float = None,
        log_filtered: bool = True
    ) -> List[KGEntity]:
        """
        M1: Filter entities by confidence threshold.

        Args:
            entities: List of extracted entities
            threshold: Minimum confidence (default: ENTITY_CONFIDENCE_THRESHOLD)
            log_filtered: Whether to log filtered entities for debugging

        Returns:
            List of entities with confidence >= threshold
        """
        if threshold is None:
            threshold = ENTITY_CONFIDENCE_THRESHOLD

        filtered = []
        low_confidence = []

        for entity in entities:
            if entity.confidence >= threshold:
                filtered.append(entity)
            else:
                low_confidence.append(entity)

        if log_filtered and low_confidence:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(
                f"[M1] Filtered {len(low_confidence)} low-confidence entities "
                f"(threshold={threshold}): {[e.label for e in low_confidence[:5]]}..."
            )

        return filtered

    def mark_high_confidence(
        self,
        entities: List[KGEntity],
        high_threshold: float = None
    ) -> List[KGEntity]:
        """
        M1: Mark high-confidence entities with a property.

        Args:
            entities: List of entities
            high_threshold: High confidence threshold (default: ENTITY_CONFIDENCE_HIGH)

        Returns:
            Entities with is_high_confidence property added
        """
        if high_threshold is None:
            high_threshold = ENTITY_CONFIDENCE_HIGH

        for entity in entities:
            entity.properties["is_high_confidence"] = entity.confidence >= high_threshold

        return entities

    async def extract_entities_filtered(
        self,
        text: str,
        entity_types: List[EntityType] = None,
        language: str = "auto",
        use_llm: bool = True,
        apply_threshold: bool = True
    ) -> List[KGEntity]:
        """
        M1: Extract entities with confidence filtering applied.

        This is a convenience method that combines extraction and filtering.

        Args:
            text: Input text
            entity_types: Types to extract
            language: Text language
            use_llm: Use LLM extraction
            apply_threshold: Whether to apply confidence threshold

        Returns:
            List of filtered entities with high-confidence marking
        """
        # Extract all entities
        entities = await self.extract_entities(
            text=text,
            entity_types=entity_types,
            language=language,
            use_llm=use_llm
        )

        # Apply confidence filtering
        if apply_threshold:
            entities = self.filter_by_confidence(entities)

        # Mark high-confidence entities
        entities = self.mark_high_confidence(entities)

        return entities


class RelationshipExtractor:
    """
    Relationship extraction between entities.

    Uses:
    - Dependency parsing
    - Pattern matching
    - LLM-based extraction
    """

    # Relationship patterns
    RELATION_PATTERNS = {
        RelationType.IS_A: [
            r'(.+?)(?:는|은|이|가)\s*(.+?)(?:이다|입니다|의 일종)',
            r'(.+?)\s+is\s+(?:a|an)\s+(.+)',
        ],
        RelationType.PART_OF: [
            r'(.+?)(?:는|은)\s*(.+?)(?:의 일부|에 속)',
            r'(.+?)\s+is\s+part\s+of\s+(.+)',
        ],
        RelationType.USES: [
            r'(.+?)(?:는|은|이|가)\s*(.+?)(?:를|을)\s*(?:사용|활용|이용)',
            r'(.+?)\s+uses\s+(.+)',
        ],
        RelationType.CAUSES: [
            r'(.+?)(?:로 인해|때문에)\s*(.+?)(?:가|이)\s*(?:발생|생김)',
            r'(.+?)\s+causes\s+(.+)',
        ],
        RelationType.RELATED_TO: [
            r'(.+?)(?:와|과)\s*(.+?)(?:는|은)\s*(?:관련|연관)',
            r'(.+?)\s+is\s+related\s+to\s+(.+)',
        ],
    }

    async def extract_relationships(
        self,
        text: str,
        entities: List[KGEntity],
        use_llm: bool = True
    ) -> List[KGRelationship]:
        """
        Extract relationships between entities from text.

        Args:
            text: Source text
            entities: Extracted entities
            use_llm: Use LLM for extraction

        Returns:
            List of relationships
        """
        relationships = []
        entity_map = {e.label.lower(): e for e in entities}

        # Pattern-based extraction
        for rel_type, patterns in self.RELATION_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if len(match) >= 2:
                        source_label = match[0].strip().lower()
                        target_label = match[1].strip().lower()

                        source_ent = entity_map.get(source_label)
                        target_ent = entity_map.get(target_label)

                        if source_ent and target_ent:
                            relationships.append(KGRelationship(
                                id=f"rel_{uuid.uuid4().hex[:8]}",
                                source_id=source_ent.id,
                                target_id=target_ent.id,
                                relation_type=rel_type,
                                confidence=0.7,
                                properties={"extraction_method": "pattern"}
                            ))

        # LLM-based relationship extraction
        if use_llm and len(entities) > 1:
            llm_rels = await self._extract_with_llm(text, entities)
            relationships.extend(llm_rels)

        # Infer additional relationships based on entity proximity
        proximity_rels = self._infer_proximity_relationships(text, entities)
        relationships.extend(proximity_rels)

        return relationships

    async def _extract_with_llm(
        self,
        text: str,
        entities: List[KGEntity]
    ) -> List[KGRelationship]:
        """Extract relationships using LLM."""
        await asyncio.sleep(0.2)

        relationships = []

        # Mock: create relationships between co-occurring entities
        for i, ent1 in enumerate(entities[:-1]):
            for ent2 in entities[i+1:]:
                # Check if entities co-occur in text
                if ent1.label in text and ent2.label in text:
                    rel_type = self._infer_relation_type(ent1, ent2, text)
                    if rel_type:
                        relationships.append(KGRelationship(
                            id=f"rel_{uuid.uuid4().hex[:8]}",
                            source_id=ent1.id,
                            target_id=ent2.id,
                            relation_type=rel_type,
                            confidence=0.8,
                            properties={"extraction_method": "llm"}
                        ))

        return relationships

    def _infer_proximity_relationships(
        self,
        text: str,
        entities: List[KGEntity]
    ) -> List[KGRelationship]:
        """Infer relationships based on entity proximity in text."""
        relationships = []

        # Find entity positions
        positions = {}
        for ent in entities:
            pos = text.find(ent.label)
            if pos >= 0:
                positions[ent.id] = pos

        # Connect entities that are close together
        sorted_entities = sorted(
            [e for e in entities if e.id in positions],
            key=lambda e: positions[e.id]
        )

        for i in range(len(sorted_entities) - 1):
            ent1 = sorted_entities[i]
            ent2 = sorted_entities[i + 1]

            distance = positions[ent2.id] - positions[ent1.id]

            # If entities are within 200 characters, they might be related
            if distance < 200:
                relationships.append(KGRelationship(
                    id=f"rel_{uuid.uuid4().hex[:8]}",
                    source_id=ent1.id,
                    target_id=ent2.id,
                    relation_type=RelationType.RELATED_TO,
                    weight=1.0 - (distance / 200),  # Closer = stronger
                    confidence=0.6,
                    properties={"extraction_method": "proximity"}
                ))

        return relationships

    def _infer_relation_type(
        self,
        source: KGEntity,
        target: KGEntity,
        text: str
    ) -> Optional[RelationType]:
        """Infer relationship type based on entity types."""
        s_type = source.entity_type
        t_type = target.entity_type

        # Technology relationships
        if s_type == EntityType.TECHNOLOGY and t_type == EntityType.TECHNOLOGY:
            return RelationType.INTEGRATES_WITH

        if s_type == EntityType.ORGANIZATION and t_type == EntityType.TECHNOLOGY:
            return RelationType.USES

        if s_type == EntityType.PERSON and t_type == EntityType.ORGANIZATION:
            return RelationType.WORKS_FOR

        if s_type == EntityType.CONCEPT and t_type == EntityType.CONCEPT:
            return RelationType.RELATED_TO

        if s_type == EntityType.PROCESS and t_type == EntityType.TECHNOLOGY:
            return RelationType.USES

        return RelationType.RELATED_TO


class KnowledgeGraphService:
    """
    Main Knowledge Graph service.

    Provides:
    - Knowledge Graph construction from text/queries
    - Entity and relationship management
    - Graph querying and traversal
    - Neo4j Cypher query generation
    - Ontology-based inference
    """

    # In-memory storage (replace with database in production)
    _knowledge_graphs: Dict[str, KnowledgeGraph] = {}
    _entities: Dict[str, KGEntity] = {}
    _relationships: Dict[str, KGRelationship] = {}

    def __init__(self):
        self.entity_extractor = EntityExtractor()
        self.relationship_extractor = RelationshipExtractor()

    async def build_knowledge_graph(
        self,
        query: str = None,
        document_ids: List[str] = None,
        name: str = None,
        description: str = None,
        max_entities: int = 100,
        max_relationships: int = 200,
        entity_types: List[EntityType] = None,
        relation_types: List[RelationType] = None,
        use_llm_extraction: bool = True,
        infer_relationships: bool = True,
        merge_similar_entities: bool = True,
        language: str = "auto",
        apply_confidence_filter: bool = True  # M1: Enable confidence filtering
    ) -> KnowledgeGraph:
        """
        Build a Knowledge Graph from query and/or documents.

        Args:
            query: Natural language query
            document_ids: Document IDs to include
            name: KG name
            description: KG description
            max_entities: Maximum entities to extract
            max_relationships: Maximum relationships
            entity_types: Entity types to include
            relation_types: Relation types to include
            use_llm_extraction: Use LLM for extraction
            infer_relationships: Infer implicit relationships
            merge_similar_entities: Merge similar entities
            language: Extraction language
            apply_confidence_filter: M1 - Filter low-confidence entities (default: True)

        Returns:
            Constructed Knowledge Graph
        """
        kg_id = f"kg_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Combine text from query and documents
        text_sources = []
        if query:
            text_sources.append(query)

        # In production, fetch document content here
        if document_ids:
            for doc_id in document_ids:
                # Mock: add placeholder text
                text_sources.append(f"Document {doc_id} content...")

        combined_text = "\n\n".join(text_sources)

        # Extract entities (M1: with confidence filtering if enabled)
        if apply_confidence_filter:
            entities = await self.entity_extractor.extract_entities_filtered(
                combined_text,
                entity_types=entity_types,
                language=language,
                use_llm=use_llm_extraction,
                apply_threshold=True
            )
        else:
            entities = await self.entity_extractor.extract_entities(
                combined_text,
                entity_types=entity_types,
                language=language,
                use_llm=use_llm_extraction
            )

        # Limit entities
        entities = entities[:max_entities]

        # Merge similar entities if requested
        if merge_similar_entities:
            entities = self._merge_similar_entities(entities)

        # Extract relationships
        relationships = await self.relationship_extractor.extract_relationships(
            combined_text,
            entities,
            use_llm=use_llm_extraction
        )

        # Filter relationships by type if specified
        if relation_types:
            relationships = [r for r in relationships if r.relation_type in relation_types]

        # Limit relationships
        relationships = relationships[:max_relationships]

        # Infer additional relationships
        if infer_relationships:
            inferred = await self._infer_relationships(entities, relationships)
            relationships.extend(inferred[:50])  # Add up to 50 inferred

        # Create Knowledge Graph
        kg = KnowledgeGraph(
            id=kg_id,
            name=name or f"KG from query: {query[:50]}..." if query else f"KG_{kg_id[:8]}",
            description=description or f"Knowledge Graph generated at {now.isoformat()}",
            entities=entities,
            relationships=relationships,
            entity_count=len(entities),
            relationship_count=len(relationships),
            source_document_ids=document_ids or [],
            source_query=query,
            created_at=now,
            updated_at=now
        )

        # Store
        self._knowledge_graphs[kg_id] = kg
        for ent in entities:
            self._entities[ent.id] = ent
        for rel in relationships:
            self._relationships[rel.id] = rel

        return kg

    def _merge_similar_entities(
        self,
        entities: List[KGEntity]
    ) -> List[KGEntity]:
        """Merge entities with similar labels."""
        merged = []
        seen = {}  # normalized_label -> entity

        for ent in entities:
            normalized = ent.label.lower().strip()

            if normalized in seen:
                # Merge: keep higher confidence
                existing = seen[normalized]
                if ent.confidence > existing.confidence:
                    existing.confidence = ent.confidence
                    existing.aliases.append(ent.label)
            else:
                seen[normalized] = ent
                merged.append(ent)

        return merged

    async def _infer_relationships(
        self,
        entities: List[KGEntity],
        existing_relationships: List[KGRelationship]
    ) -> List[KGRelationship]:
        """Infer implicit relationships using reasoning rules."""
        inferred = []
        existing_pairs = {
            (r.source_id, r.target_id) for r in existing_relationships
        }

        # Rule 1: Transitive relationships
        # If A relates_to B and B relates_to C, then A may relate_to C
        entity_map = {e.id: e for e in entities}
        adjacency = defaultdict(set)

        for rel in existing_relationships:
            adjacency[rel.source_id].add(rel.target_id)

        for a in entity_map:
            for b in adjacency[a]:
                for c in adjacency[b]:
                    if a != c and (a, c) not in existing_pairs:
                        inferred.append(KGRelationship(
                            id=f"rel_{uuid.uuid4().hex[:8]}",
                            source_id=a,
                            target_id=c,
                            relation_type=RelationType.RELATED_TO,
                            confidence=0.5,
                            inferred=True,
                            properties={"rule": "transitivity"}
                        ))
                        existing_pairs.add((a, c))

        # Rule 2: Same-type clustering
        # Entities of the same type are likely related
        by_type = defaultdict(list)
        for ent in entities:
            by_type[ent.entity_type].append(ent)

        for entity_type, group in by_type.items():
            if len(group) > 1 and entity_type in [EntityType.TECHNOLOGY, EntityType.CONCEPT]:
                for i, e1 in enumerate(group[:-1]):
                    e2 = group[i + 1]
                    if (e1.id, e2.id) not in existing_pairs:
                        inferred.append(KGRelationship(
                            id=f"rel_{uuid.uuid4().hex[:8]}",
                            source_id=e1.id,
                            target_id=e2.id,
                            relation_type=RelationType.SIMILAR_TO,
                            confidence=0.4,
                            inferred=True,
                            properties={"rule": "same_type"}
                        ))
                        existing_pairs.add((e1.id, e2.id))

        return inferred

    async def query_knowledge_graph(
        self,
        knowledge_graph_id: str,
        query: str,
        max_hops: int = 3,
        include_paths: bool = True,
        use_embeddings: bool = True
    ) -> Dict[str, Any]:
        """
        Query a Knowledge Graph using natural language.

        Args:
            knowledge_graph_id: KG ID to query
            query: Natural language query
            max_hops: Maximum traversal depth
            include_paths: Include relationship paths
            use_embeddings: Use vector similarity

        Returns:
            Query results with answer, entities, and paths
        """
        kg = self._knowledge_graphs.get(knowledge_graph_id)
        if not kg:
            raise ValueError(f"Knowledge Graph not found: {knowledge_graph_id}")

        # Extract query entities
        query_entities = await self.entity_extractor.extract_entities(
            query, use_llm=False
        )

        query_terms = set(e.label.lower() for e in query_entities)
        query_terms.update(query.lower().split())

        # Find relevant entities
        relevant_entities = []
        for ent in kg.entities:
            score = self._compute_relevance(ent, query_terms)
            if score > 0:
                ent_copy = ent.model_copy()
                ent_copy.properties["relevance_score"] = score
                relevant_entities.append(ent_copy)

        relevant_entities.sort(
            key=lambda e: e.properties.get("relevance_score", 0),
            reverse=True
        )
        relevant_entities = relevant_entities[:20]

        # Find relevant relationships
        relevant_entity_ids = {e.id for e in relevant_entities}
        relevant_relationships = [
            rel for rel in kg.relationships
            if rel.source_id in relevant_entity_ids or rel.target_id in relevant_entity_ids
        ]

        # Find paths between entities
        paths = []
        if include_paths and len(relevant_entities) >= 2:
            paths = self._find_paths(
                kg,
                [e.id for e in relevant_entities[:5]],
                max_hops
            )

        # Generate answer
        answer = self._generate_answer(query, relevant_entities, relevant_relationships)

        # Generate Cypher query
        cypher = self._generate_cypher(query, relevant_entities)

        return {
            "answer": answer,
            "relevant_entities": relevant_entities,
            "relevant_relationships": relevant_relationships,
            "paths": paths,
            "confidence": 0.8 if relevant_entities else 0.3,
            "cypher_query": cypher
        }

    def _compute_relevance(
        self,
        entity: KGEntity,
        query_terms: Set[str]
    ) -> float:
        """Compute entity relevance to query."""
        score = 0.0
        entity_terms = entity.label.lower().split()

        # Exact match
        if entity.label.lower() in query_terms:
            score += 1.0

        # Partial match
        for term in entity_terms:
            if term in query_terms:
                score += 0.5

        # Alias match
        for alias in entity.aliases:
            if alias.lower() in query_terms:
                score += 0.3

        # Description match
        if entity.description:
            desc_terms = entity.description.lower().split()
            for term in desc_terms:
                if term in query_terms:
                    score += 0.1

        return score

    def _find_paths(
        self,
        kg: KnowledgeGraph,
        entity_ids: List[str],
        max_hops: int
    ) -> List[List[str]]:
        """Find paths between entities in the graph."""
        paths = []

        # Build adjacency list
        adjacency = defaultdict(list)
        for rel in kg.relationships:
            adjacency[rel.source_id].append((rel.target_id, rel.relation_type.value))
            if rel.bidirectional:
                adjacency[rel.target_id].append((rel.source_id, rel.relation_type.value))

        # BFS for paths
        for i, start_id in enumerate(entity_ids[:-1]):
            for end_id in entity_ids[i+1:]:
                path = self._bfs_path(adjacency, start_id, end_id, max_hops)
                if path:
                    paths.append(path)

        return paths[:10]  # Limit paths

    def _bfs_path(
        self,
        adjacency: Dict[str, List[Tuple[str, str]]],
        start: str,
        end: str,
        max_depth: int
    ) -> Optional[List[str]]:
        """BFS to find path between two nodes."""
        if start == end:
            return [start]

        visited = {start}
        queue = [(start, [start])]

        while queue:
            node, path = queue.pop(0)

            if len(path) > max_depth:
                continue

            for neighbor, rel_type in adjacency.get(node, []):
                if neighbor == end:
                    return path + [f"-[{rel_type}]->", neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [f"-[{rel_type}]->", neighbor]))

        return None

    def _generate_answer(
        self,
        query: str,
        entities: List[KGEntity],
        relationships: List[KGRelationship]
    ) -> str:
        """Generate natural language answer from graph results."""
        if not entities:
            return "관련된 정보를 찾을 수 없습니다."

        # Build answer from entities and relationships
        entity_labels = [e.label for e in entities[:5]]
        answer_parts = []

        answer_parts.append(f"질의 '{query[:50]}...'에 관련된 주요 개념:")
        answer_parts.append(", ".join(entity_labels))

        if relationships:
            rel_desc = []
            entity_map = {e.id: e.label for e in entities}
            for rel in relationships[:5]:
                source = entity_map.get(rel.source_id, "?")
                target = entity_map.get(rel.target_id, "?")
                rel_desc.append(f"- {source} --[{rel.relation_type.value}]--> {target}")

            if rel_desc:
                answer_parts.append("\n주요 관계:")
                answer_parts.extend(rel_desc)

        return "\n".join(answer_parts)

    def _generate_cypher(
        self,
        query: str,
        entities: List[KGEntity]
    ) -> str:
        """Generate Neo4j Cypher query for the search."""
        if not entities:
            return f"MATCH (n) WHERE n.label CONTAINS '{query[:50]}' RETURN n LIMIT 10"

        entity_labels = [e.label for e in entities[:3]]
        labels_pattern = "|".join(f"'{lbl}'" for lbl in entity_labels)

        cypher = f"""
MATCH (n)-[r]-(m)
WHERE n.label IN [{labels_pattern}]
OR m.label IN [{labels_pattern}]
RETURN n, r, m
LIMIT 50
""".strip()

        return cypher

    async def get_knowledge_graph(self, kg_id: str) -> Optional[KnowledgeGraph]:
        """Get Knowledge Graph by ID."""
        return self._knowledge_graphs.get(kg_id)

    async def list_knowledge_graphs(
        self,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """List all Knowledge Graphs."""
        kgs = list(self._knowledge_graphs.values())
        kgs.sort(key=lambda x: x.created_at, reverse=True)

        total = len(kgs)
        start = (page - 1) * limit
        end = start + limit

        summaries = []
        for kg in kgs[start:end]:
            entity_types = defaultdict(int)
            for ent in kg.entities:
                entity_types[ent.entity_type.value] += 1

            relation_types = defaultdict(int)
            for rel in kg.relationships:
                relation_types[rel.relation_type.value] += 1

            summaries.append(KGSummary(
                id=kg.id,
                name=kg.name,
                description=kg.description,
                entity_count=kg.entity_count,
                relationship_count=kg.relationship_count,
                entity_types=dict(entity_types),
                relation_types=dict(relation_types),
                created_at=kg.created_at,
                updated_at=kg.updated_at
            ))

        return {"knowledge_graphs": summaries, "total": total}

    async def delete_knowledge_graph(self, kg_id: str) -> bool:
        """Delete a Knowledge Graph."""
        if kg_id not in self._knowledge_graphs:
            return False

        kg = self._knowledge_graphs[kg_id]

        # Remove entities and relationships
        for ent in kg.entities:
            self._entities.pop(ent.id, None)
        for rel in kg.relationships:
            self._relationships.pop(rel.id, None)

        del self._knowledge_graphs[kg_id]
        return True

    async def expand_entity(
        self,
        entity_id: str,
        max_depth: int = 2,
        max_neighbors: int = 20,
        relation_types: List[RelationType] = None
    ) -> Dict[str, Any]:
        """Expand an entity with its neighbors."""
        entity = self._entities.get(entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_id}")

        # Find connected entities
        connected = []
        relationships = []

        for rel in self._relationships.values():
            if relation_types and rel.relation_type not in relation_types:
                continue

            if rel.source_id == entity_id:
                target = self._entities.get(rel.target_id)
                if target:
                    connected.append(target)
                    relationships.append(rel)
            elif rel.target_id == entity_id:
                source = self._entities.get(rel.source_id)
                if source:
                    connected.append(source)
                    relationships.append(rel)

        # Limit results
        connected = connected[:max_neighbors]
        relationships = relationships[:max_neighbors]

        return {
            "center_entity": entity,
            "expanded_entities": connected,
            "relationships": relationships,
            "depth_reached": 1
        }

    async def export_to_cypher(
        self,
        kg_id: str,
        include_properties: bool = True
    ) -> str:
        """Export Knowledge Graph to Cypher CREATE statements."""
        kg = self._knowledge_graphs.get(kg_id)
        if not kg:
            raise ValueError(f"Knowledge Graph not found: {kg_id}")

        statements = []

        # Create nodes
        for ent in kg.entities:
            props = {"id": ent.id, "label": ent.label}
            if include_properties:
                props.update(ent.properties)

            props_str = ", ".join(f'{k}: "{v}"' for k, v in props.items() if isinstance(v, str))
            stmt = f'CREATE (:{ent.entity_type.value} {{{props_str}}})'
            statements.append(stmt)

        # Create relationships
        for rel in kg.relationships:
            source_ent = next((e for e in kg.entities if e.id == rel.source_id), None)
            target_ent = next((e for e in kg.entities if e.id == rel.target_id), None)

            if source_ent and target_ent:
                stmt = f'''
MATCH (a:{source_ent.entity_type.value} {{id: "{source_ent.id}"}})
MATCH (b:{target_ent.entity_type.value} {{id: "{target_ent.id}"}})
CREATE (a)-[:{rel.relation_type.value}]->(b)'''
                statements.append(stmt.strip())

        return ";\n\n".join(statements) + ";"


# =========================================================================
# H1: Chunk Similarity Relations Service (Neo4j-based)
# =========================================================================

# H1 Constants
SIMILARITY_THRESHOLD = 0.80  # Minimum cosine similarity for SIMILAR_TO relation
MAX_SIMILAR_RELATIONS = 5    # Max similar relations per chunk
CO_MENTIONS_MIN_ENTITIES = 2 # Min common entities for CO_MENTIONS relation

# =========================================================================
# M1: Entity Confidence Threshold Constants
# =========================================================================
ENTITY_CONFIDENCE_THRESHOLD = 0.70  # Minimum confidence to store entity (70%)
ENTITY_CONFIDENCE_HIGH = 0.90       # High confidence threshold for labeling (90%)


class ChunkRelationService:
    """
    Service for creating and querying chunk-to-chunk relationships in Neo4j.

    Provides:
    - SIMILAR_TO: Semantic similarity between chunks (cosine >= 0.8)
    - CO_MENTIONS: Chunks mentioning same entities
    - Graph-based context expansion for RAG

    Usage:
        from langchain_neo4j import Neo4jGraph
        graph = Neo4jGraph(url=..., username=..., password=...)
        service = ChunkRelationService(graph)
        await service.create_similarity_relations(document_id)
    """

    def __init__(self, graph):
        """
        Initialize with Neo4j graph connection.

        Args:
            graph: langchain_neo4j.Neo4jGraph instance
        """
        self.graph = graph

    async def create_chunk_similarity_relations(
        self,
        document_id: str,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        max_relations: int = MAX_SIMILAR_RELATIONS
    ) -> Dict[str, Any]:
        """
        Create SIMILAR_TO relations between semantically similar chunks.

        Uses cosine similarity on chunk embeddings stored in Neo4j.
        Only creates relations where similarity >= threshold.

        Args:
            document_id: Document ID to process
            similarity_threshold: Minimum similarity (0-1)
            max_relations: Max relations per chunk

        Returns:
            Dict with created_count, skipped_count, errors
        """
        # Note: This query requires Neo4j GDS or vector index for cosine similarity
        # Alternative: Use manual calculation if GDS not available
        query = """
        MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c1:Chunk)
        WHERE c1.embedding IS NOT NULL
        WITH c1, d
        MATCH (d)-[:CONTAINS]->(c2:Chunk)
        WHERE c2.embedding IS NOT NULL
          AND id(c1) < id(c2)
        WITH c1, c2,
             reduce(dot = 0.0, i IN range(0, size(c1.embedding)-1) |
                dot + c1.embedding[i] * c2.embedding[i]) /
             (sqrt(reduce(s1 = 0.0, x IN c1.embedding | s1 + x*x)) *
              sqrt(reduce(s2 = 0.0, y IN c2.embedding | s2 + y*y))) AS similarity
        WHERE similarity >= $threshold
        WITH c1, c2, similarity
        ORDER BY similarity DESC
        WITH c1, collect({chunk: c2, score: similarity})[0..$max_rels] as top_similar
        UNWIND top_similar as sim
        MERGE (c1)-[r:SIMILAR_TO]->(sim.chunk)
        SET r.score = sim.score,
            r.created_at = datetime(),
            r.method = 'cosine_similarity'
        RETURN count(r) as created_count
        """

        try:
            result = self.graph.query(query, {
                "doc_id": document_id,
                "threshold": similarity_threshold,
                "max_rels": max_relations
            })

            created_count = result[0]["created_count"] if result else 0

            return {
                "success": True,
                "created_count": created_count,
                "document_id": document_id,
                "threshold": similarity_threshold
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }

    async def create_co_mentions_relations(
        self,
        document_id: str,
        min_common_entities: int = CO_MENTIONS_MIN_ENTITIES
    ) -> Dict[str, Any]:
        """
        Create CO_MENTIONS relations between chunks sharing entities.

        Two chunks are connected if they both MENTION the same entities.

        Args:
            document_id: Document ID to process
            min_common_entities: Minimum shared entities required

        Returns:
            Dict with created_count and details
        """
        query = """
        MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c1:Chunk)
        MATCH (d)-[:CONTAINS]->(c2:Chunk)
        WHERE id(c1) < id(c2)
        MATCH (c1)-[:MENTIONS]->(e:Entity)<-[:MENTIONS]-(c2)
        WITH c1, c2, collect(DISTINCT e.name) as common_entities
        WHERE size(common_entities) >= $min_entities
        MERGE (c1)-[r:CO_MENTIONS]->(c2)
        SET r.entities = common_entities,
            r.count = size(common_entities),
            r.created_at = datetime()
        RETURN count(r) as created_count
        """

        try:
            result = self.graph.query(query, {
                "doc_id": document_id,
                "min_entities": min_common_entities
            })

            created_count = result[0]["created_count"] if result else 0

            return {
                "success": True,
                "created_count": created_count,
                "document_id": document_id,
                "min_common_entities": min_common_entities
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }

    async def create_all_chunk_relations(
        self,
        document_id: str,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
        min_common_entities: int = CO_MENTIONS_MIN_ENTITIES
    ) -> Dict[str, Any]:
        """
        Create all chunk-to-chunk relations for a document.

        Combines SIMILAR_TO and CO_MENTIONS relation creation.

        Args:
            document_id: Document ID
            similarity_threshold: For SIMILAR_TO
            min_common_entities: For CO_MENTIONS

        Returns:
            Combined results
        """
        similar_result = await self.create_chunk_similarity_relations(
            document_id, similarity_threshold
        )

        co_mentions_result = await self.create_co_mentions_relations(
            document_id, min_common_entities
        )

        return {
            "document_id": document_id,
            "similar_to": similar_result,
            "co_mentions": co_mentions_result,
            "total_relations": (
                (similar_result.get("created_count", 0) if similar_result.get("success") else 0) +
                (co_mentions_result.get("created_count", 0) if co_mentions_result.get("success") else 0)
            )
        }

    # =========================================================================
    # M2: Chunk Overlap Relations
    # =========================================================================

    async def create_overlap_relations(
        self,
        document_id: str
    ) -> Dict[str, Any]:
        """
        M2: Create OVERLAPS relations between sequential chunks.

        Finds chunks with NEXT relations and creates OVERLAPS to track
        content continuity between adjacent chunks.

        Args:
            document_id: Document ID to process

        Returns:
            Dict with created_count and details
        """
        query = """
        MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c1:Chunk)-[:NEXT]->(c2:Chunk)
        WHERE NOT EXISTS((c1)-[:OVERLAPS]->(c2))
        WITH c1, c2,
             CASE
                 WHEN size(c1.content) > 100 AND size(c2.content) > 100
                 THEN substring(c1.content, size(c1.content) - 100)
                 ELSE ''
             END as tail_text,
             CASE
                 WHEN size(c1.content) > 100 AND size(c2.content) > 100
                 THEN substring(c2.content, 0, 100)
                 ELSE ''
             END as head_text
        WHERE tail_text <> '' AND head_text <> ''
        CREATE (c1)-[r:OVERLAPS {
            chars: 100,
            position: 'end-start',
            tail_hash: left(toString(abs(reduce(h = 0, c IN split(tail_text, '') | h + toInteger(c)))), 8),
            created_at: datetime()
        }]->(c2)
        RETURN count(r) as created_count
        """

        try:
            result = self.graph.query(query, {"doc_id": document_id})
            created_count = result[0]["created_count"] if result else 0

            return {
                "success": True,
                "created_count": created_count,
                "document_id": document_id
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }

    async def create_overlap_relation_single(
        self,
        source_chunk_id: str,
        target_chunk_id: str,
        overlap_text: str,
        overlap_chars: int,
        position: str = "end-start"
    ) -> Dict[str, Any]:
        """
        M2: Create a single OVERLAPS relation between two chunks.

        Args:
            source_chunk_id: Source chunk ID (has tail overlap)
            target_chunk_id: Target chunk ID (has head overlap)
            overlap_text: The overlapping text content
            overlap_chars: Number of overlapping characters
            position: Position description (default: end-start)

        Returns:
            Dict with success status
        """
        import hashlib
        text_hash = hashlib.md5(overlap_text.encode()).hexdigest()[:8]

        query = """
        MATCH (c1:Chunk {id: $source_id})
        MATCH (c2:Chunk {id: $target_id})
        MERGE (c1)-[r:OVERLAPS]->(c2)
        SET r.chars = $chars,
            r.position = $position,
            r.text_hash = $text_hash,
            r.created_at = datetime()
        RETURN r IS NOT NULL as success
        """

        try:
            result = self.graph.query(query, {
                "source_id": source_chunk_id,
                "target_id": target_chunk_id,
                "chars": overlap_chars,
                "position": position,
                "text_hash": text_hash
            })

            return {
                "success": True,
                "source_chunk_id": source_chunk_id,
                "target_chunk_id": target_chunk_id,
                "overlap_chars": overlap_chars
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def get_overlapping_chunks(
        self,
        chunk_id: str
    ) -> List[Dict[str, Any]]:
        """
        M2: Get chunks that overlap with a given chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            List of overlapping chunks with overlap info
        """
        query = """
        MATCH (c:Chunk {id: $chunk_id})-[r:OVERLAPS]-(related:Chunk)
        RETURN
            related.id as chunk_id,
            related.content as content,
            related.page_number as page_number,
            r.chars as overlap_chars,
            r.position as position,
            CASE
                WHEN startNode(r) = c THEN 'outgoing'
                ELSE 'incoming'
            END as direction
        ORDER BY related.chunk_index
        """

        result = self.graph.query(query, {"chunk_id": chunk_id})
        return [dict(row) for row in result]

    async def get_similar_chunks(
        self,
        chunk_id: str,
        min_score: float = 0.7,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get chunks similar to a given chunk.

        Args:
            chunk_id: Source chunk ID
            min_score: Minimum similarity score
            limit: Max results

        Returns:
            List of similar chunks with scores
        """
        query = """
        MATCH (c:Chunk {id: $chunk_id})-[r:SIMILAR_TO]-(similar:Chunk)
        WHERE r.score >= $min_score
        RETURN similar.id as chunk_id,
               similar.content as content,
               r.score as similarity,
               similar.page_number as page_number
        ORDER BY r.score DESC
        LIMIT $limit
        """

        result = self.graph.query(query, {
            "chunk_id": chunk_id,
            "min_score": min_score,
            "limit": limit
        })

        return [dict(row) for row in result]

    async def get_co_mentioning_chunks(
        self,
        chunk_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get chunks that share entity mentions with given chunk.

        Args:
            chunk_id: Source chunk ID
            limit: Max results

        Returns:
            List of co-mentioning chunks with shared entities
        """
        query = """
        MATCH (c:Chunk {id: $chunk_id})-[r:CO_MENTIONS]-(related:Chunk)
        RETURN related.id as chunk_id,
               related.content as content,
               r.entities as shared_entities,
               r.count as entity_count
        ORDER BY r.count DESC
        LIMIT $limit
        """

        result = self.graph.query(query, {
            "chunk_id": chunk_id,
            "limit": limit
        })

        return [dict(row) for row in result]

    async def expand_context(
        self,
        chunk_ids: List[str],
        depth: int = 2,
        include_similar: bool = True,
        include_co_mentions: bool = True,
        include_next: bool = True,
        include_overlaps: bool = True,
        include_section_siblings: bool = True
    ) -> Dict[str, Any]:
        """
        Expand context by following chunk relations.

        Used by RAG to gather related chunks for better context.

        Args:
            chunk_ids: Starting chunk IDs
            depth: Max relation hops
            include_similar: Include SIMILAR_TO relations
            include_co_mentions: Include CO_MENTIONS relations
            include_next: Include NEXT relations
            include_overlaps: Include OVERLAPS relations (M2)
            include_section_siblings: Include chunks from same section (M3)

        Returns:
            Dict with source chunks, related chunks, and relation info
        """
        rel_types = []
        if include_similar:
            rel_types.append("SIMILAR_TO")
        if include_co_mentions:
            rel_types.append("CO_MENTIONS")
        if include_next:
            rel_types.append("NEXT")
        if include_overlaps:
            rel_types.append("OVERLAPS")

        if not rel_types:
            return {"source_chunks": chunk_ids, "related_chunks": [], "relations": []}

        rel_pattern = "|".join(rel_types)

        query = f"""
        MATCH (c:Chunk)
        WHERE c.id IN $chunk_ids
        CALL {{
            WITH c
            MATCH path = (c)-[:{rel_pattern}*1..{depth}]-(related:Chunk)
            WHERE related.id <> c.id
            RETURN DISTINCT related,
                   length(path) as distance,
                   [r IN relationships(path) | type(r)] as rel_types
            ORDER BY distance
            LIMIT 10
        }}
        RETURN c.id as source_id,
               collect({{
                   chunk_id: related.id,
                   content: related.content,
                   page_number: related.page_number,
                   distance: distance,
                   via_relations: rel_types
               }}) as related_chunks
        """

        result = self.graph.query(query, {"chunk_ids": chunk_ids})

        # Flatten and deduplicate results
        all_related = {}
        for row in result:
            for chunk in row["related_chunks"]:
                chunk_id = chunk["chunk_id"]
                if chunk_id not in all_related or chunk["distance"] < all_related[chunk_id]["distance"]:
                    all_related[chunk_id] = chunk

        # M3: Include section siblings
        if include_section_siblings:
            section_query = """
            MATCH (c:Chunk)
            WHERE c.id IN $chunk_ids AND c.section_id IS NOT NULL
            MATCH (s:Section {id: c.section_id})-[:CONTAINS_CHUNK]->(sibling:Chunk)
            WHERE sibling.id <> c.id AND NOT sibling.id IN $chunk_ids
            RETURN DISTINCT sibling.id as chunk_id,
                   sibling.content as content,
                   sibling.page_number as page_number,
                   1 as distance,
                   ['SECTION_SIBLING'] as via_relations
            LIMIT 10
            """
            section_result = self.graph.query(section_query, {"chunk_ids": chunk_ids})

            for row in section_result:
                chunk_id = row["chunk_id"]
                if chunk_id not in all_related:
                    all_related[chunk_id] = dict(row)

        return {
            "source_chunks": chunk_ids,
            "related_chunks": list(all_related.values()),
            "total_related": len(all_related)
        }

    async def get_chunk_relation_stats(
        self,
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about chunk relations.

        Args:
            document_id: Optional filter by document

        Returns:
            Relation counts and statistics
        """
        if document_id:
            query = """
            MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)
            OPTIONAL MATCH (c)-[sim:SIMILAR_TO]-()
            OPTIONAL MATCH (c)-[co:CO_MENTIONS]-()
            OPTIONAL MATCH (c)-[next:NEXT]-()
            RETURN
                count(DISTINCT c) as total_chunks,
                count(DISTINCT sim) as similar_to_count,
                count(DISTINCT co) as co_mentions_count,
                count(DISTINCT next) as next_count,
                avg(sim.score) as avg_similarity
            """
            result = self.graph.query(query, {"doc_id": document_id})
        else:
            query = """
            MATCH (c:Chunk)
            OPTIONAL MATCH (c)-[sim:SIMILAR_TO]-()
            OPTIONAL MATCH (c)-[co:CO_MENTIONS]-()
            OPTIONAL MATCH (c)-[next:NEXT]-()
            RETURN
                count(DISTINCT c) as total_chunks,
                count(DISTINCT sim) as similar_to_count,
                count(DISTINCT co) as co_mentions_count,
                count(DISTINCT next) as next_count,
                avg(sim.score) as avg_similarity
            """
            result = self.graph.query(query)

        if result:
            row = result[0]
            return {
                "total_chunks": row["total_chunks"],
                "relations": {
                    "SIMILAR_TO": row["similar_to_count"],
                    "CO_MENTIONS": row["co_mentions_count"],
                    "NEXT": row["next_count"]
                },
                "avg_similarity_score": row["avg_similarity"]
            }

        return {"total_chunks": 0, "relations": {}, "avg_similarity_score": None}

    # =========================================================================
    # M1: Entity Confidence Operations in Neo4j
    # =========================================================================

    async def label_high_confidence_entities(
        self,
        document_id: Optional[str] = None,
        threshold: float = ENTITY_CONFIDENCE_HIGH
    ) -> Dict[str, Any]:
        """
        M1: Add HighConfidenceEntity label to entities above threshold.

        Args:
            document_id: Optional document filter
            threshold: Confidence threshold (default: 0.9)

        Returns:
            Dict with labeled_count and details
        """
        if document_id:
            query = """
            MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            WHERE e.confidence >= $threshold
              AND NOT e:HighConfidenceEntity
            SET e:HighConfidenceEntity
            RETURN count(DISTINCT e) as labeled_count
            """
            params = {"doc_id": document_id, "threshold": threshold}
        else:
            query = """
            MATCH (e:Entity)
            WHERE e.confidence >= $threshold
              AND NOT e:HighConfidenceEntity
            SET e:HighConfidenceEntity
            RETURN count(e) as labeled_count
            """
            params = {"threshold": threshold}

        try:
            result = self.graph.query(query, params)
            labeled_count = result[0]["labeled_count"] if result else 0

            return {
                "success": True,
                "labeled_count": labeled_count,
                "threshold": threshold,
                "document_id": document_id
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id
            }

    async def get_entity_confidence_stats(
        self,
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        M1: Get entity confidence statistics.

        Args:
            document_id: Optional document filter

        Returns:
            Statistics about entity confidence distribution
        """
        if document_id:
            query = """
            MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)-[:MENTIONS]->(e:Entity)
            WITH DISTINCT e
            RETURN
                count(e) as total_entities,
                count(CASE WHEN e.confidence >= $high_threshold THEN 1 END) as high_confidence_count,
                count(CASE WHEN e.confidence >= $threshold AND e.confidence < $high_threshold THEN 1 END) as medium_confidence_count,
                count(CASE WHEN e.confidence < $threshold THEN 1 END) as low_confidence_count,
                avg(e.confidence) as avg_confidence,
                count(CASE WHEN e:HighConfidenceEntity THEN 1 END) as labeled_high_count
            """
            params = {
                "doc_id": document_id,
                "threshold": ENTITY_CONFIDENCE_THRESHOLD,
                "high_threshold": ENTITY_CONFIDENCE_HIGH
            }
        else:
            query = """
            MATCH (e:Entity)
            RETURN
                count(e) as total_entities,
                count(CASE WHEN e.confidence >= $high_threshold THEN 1 END) as high_confidence_count,
                count(CASE WHEN e.confidence >= $threshold AND e.confidence < $high_threshold THEN 1 END) as medium_confidence_count,
                count(CASE WHEN e.confidence < $threshold THEN 1 END) as low_confidence_count,
                avg(e.confidence) as avg_confidence,
                count(CASE WHEN e:HighConfidenceEntity THEN 1 END) as labeled_high_count
            """
            params = {
                "threshold": ENTITY_CONFIDENCE_THRESHOLD,
                "high_threshold": ENTITY_CONFIDENCE_HIGH
            }

        try:
            result = self.graph.query(query, params)
            if result:
                row = result[0]
                total = row["total_entities"] or 0
                high = row["high_confidence_count"] or 0

                return {
                    "total_entities": total,
                    "high_confidence_count": high,
                    "medium_confidence_count": row["medium_confidence_count"] or 0,
                    "low_confidence_count": row["low_confidence_count"] or 0,
                    "avg_confidence": row["avg_confidence"],
                    "labeled_high_count": row["labeled_high_count"] or 0,
                    "high_confidence_ratio": high / total if total > 0 else 0,
                    "thresholds": {
                        "low": ENTITY_CONFIDENCE_THRESHOLD,
                        "high": ENTITY_CONFIDENCE_HIGH
                    }
                }
            return {"total_entities": 0}
        except Exception as e:
            return {"error": str(e)}

    # =========================================================================
    # M3: Section Hierarchy Operations
    # =========================================================================

    async def create_section_node(
        self,
        document_id: str,
        section_id: str,
        title: str,
        level: int,
        path: str,
        page_start: int,
        page_end: int,
        parent_section_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        M3: Create a Section node and link it to Document or parent Section.

        Args:
            document_id: Document ID
            section_id: Unique section ID
            title: Section title
            level: Hierarchy level (1=chapter, 2=section, 3=subsection)
            path: Section path (e.g., "1", "1.1", "1.1.2")
            page_start: Starting page
            page_end: Ending page
            parent_section_id: Optional parent section ID

        Returns:
            Dict with success status and section details
        """
        # Create Section node
        create_query = """
        MERGE (s:Section {id: $section_id})
        SET s.title = $title,
            s.level = $level,
            s.path = $path,
            s.page_start = $page_start,
            s.page_end = $page_end,
            s.document_id = $document_id,
            s.created_at = datetime()
        RETURN s.id as section_id
        """

        try:
            self.graph.query(create_query, {
                "section_id": section_id,
                "title": title,
                "level": level,
                "path": path,
                "page_start": page_start,
                "page_end": page_end,
                "document_id": document_id
            })

            # Link to parent (Document or Section)
            if parent_section_id:
                # Link Section → Section
                link_query = """
                MATCH (parent:Section {id: $parent_id})
                MATCH (child:Section {id: $child_id})
                MERGE (parent)-[:HAS_SECTION]->(child)
                """
                self.graph.query(link_query, {
                    "parent_id": parent_section_id,
                    "child_id": section_id
                })
            else:
                # Link Document → Section (top-level section)
                link_query = """
                MATCH (d:Document {id: $doc_id})
                MATCH (s:Section {id: $section_id})
                MERGE (d)-[:HAS_SECTION]->(s)
                """
                self.graph.query(link_query, {
                    "doc_id": document_id,
                    "section_id": section_id
                })

            return {
                "success": True,
                "section_id": section_id,
                "title": title,
                "level": level,
                "path": path
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def link_chunk_to_section(
        self,
        chunk_id: str,
        section_id: str
    ) -> Dict[str, Any]:
        """
        M3: Link a Chunk to its containing Section.

        Args:
            chunk_id: Chunk ID
            section_id: Section ID

        Returns:
            Dict with success status
        """
        query = """
        MATCH (s:Section {id: $section_id})
        MATCH (c:Chunk {id: $chunk_id})
        MERGE (s)-[:CONTAINS_CHUNK]->(c)
        SET c.section_id = $section_id
        RETURN s.id as section_id, c.id as chunk_id
        """

        try:
            result = self.graph.query(query, {
                "section_id": section_id,
                "chunk_id": chunk_id
            })

            if result:
                return {
                    "success": True,
                    "section_id": section_id,
                    "chunk_id": chunk_id
                }
            return {
                "success": False,
                "error": "No match found"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def get_chunks_by_section(
        self,
        section_path: str,
        document_id: Optional[str] = None,
        include_subsections: bool = True
    ) -> List[Dict[str, Any]]:
        """
        M3: Get all chunks within a section (and optionally subsections).

        Args:
            section_path: Section path (e.g., "2" for chapter 2, "2.1" for section 2.1)
            document_id: Optional document filter
            include_subsections: Include chunks from child sections

        Returns:
            List of chunks with section info
        """
        if include_subsections:
            # Use STARTS WITH for path prefix matching
            path_filter = "s.path STARTS WITH $section_path"
        else:
            path_filter = "s.path = $section_path"

        if document_id:
            query = f"""
            MATCH (d:Document {{id: $doc_id}})-[:HAS_SECTION*1..]->(s:Section)
            WHERE {path_filter}
            MATCH (s)-[:CONTAINS_CHUNK]->(c:Chunk)
            RETURN c.id as chunk_id,
                   c.content as content,
                   c.page_number as page_number,
                   s.path as section_path,
                   s.title as section_title,
                   s.level as section_level
            ORDER BY s.path, c.chunk_index
            """
            params = {"doc_id": document_id, "section_path": section_path}
        else:
            query = f"""
            MATCH (s:Section)-[:CONTAINS_CHUNK]->(c:Chunk)
            WHERE {path_filter}
            RETURN c.id as chunk_id,
                   c.content as content,
                   c.page_number as page_number,
                   s.path as section_path,
                   s.title as section_title,
                   s.level as section_level
            ORDER BY s.path, c.chunk_index
            """
            params = {"section_path": section_path}

        result = self.graph.query(query, params)
        return [dict(row) for row in result]

    async def get_section_hierarchy(
        self,
        document_id: str
    ) -> List[Dict[str, Any]]:
        """
        M3: Get the complete section hierarchy for a document.

        Args:
            document_id: Document ID

        Returns:
            List of sections with hierarchy info
        """
        query = """
        MATCH (d:Document {id: $doc_id})-[:HAS_SECTION*1..]->(s:Section)
        OPTIONAL MATCH (s)-[:CONTAINS_CHUNK]->(c:Chunk)
        WITH s, count(c) as chunk_count
        OPTIONAL MATCH (parent:Section)-[:HAS_SECTION]->(s)
        RETURN s.id as section_id,
               s.title as title,
               s.level as level,
               s.path as path,
               s.page_start as page_start,
               s.page_end as page_end,
               parent.id as parent_section_id,
               chunk_count
        ORDER BY s.path
        """

        result = self.graph.query(query, {"doc_id": document_id})
        return [dict(row) for row in result]

    async def build_section_hierarchy_from_chunks(
        self,
        document_id: str
    ) -> Dict[str, Any]:
        """
        M3: Build section hierarchy from existing chunk section_path metadata.

        Extracts unique section paths from chunks and creates Section nodes.

        Args:
            document_id: Document ID

        Returns:
            Dict with created sections count and details
        """
        # Get unique section paths from chunks
        query = """
        MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)
        WHERE c.section_path IS NOT NULL AND c.section_path <> ''
        WITH DISTINCT c.section_path as path, c.section_title as title,
             min(c.page_number) as page_start,
             max(c.page_number) as page_end
        RETURN path, title, page_start, page_end
        ORDER BY path
        """

        result = self.graph.query(query, {"doc_id": document_id})

        created_sections = []
        for row in result:
            path = row["path"]
            title = row["title"] or f"Section {path}"
            level = len(path.split(".")) if path else 1

            # Determine parent section
            parts = path.split(".")
            parent_path = ".".join(parts[:-1]) if len(parts) > 1 else None
            parent_section_id = f"{document_id}_sec_{parent_path}" if parent_path else None

            section_id = f"{document_id}_sec_{path}"

            section_result = await self.create_section_node(
                document_id=document_id,
                section_id=section_id,
                title=title,
                level=level,
                path=path,
                page_start=row["page_start"] or 1,
                page_end=row["page_end"] or 1,
                parent_section_id=parent_section_id
            )

            if section_result.get("success"):
                created_sections.append(section_result)

        # Link chunks to their sections
        link_query = """
        MATCH (d:Document {id: $doc_id})-[:CONTAINS]->(c:Chunk)
        WHERE c.section_path IS NOT NULL AND c.section_path <> ''
        MATCH (s:Section {path: c.section_path, document_id: $doc_id})
        MERGE (s)-[:CONTAINS_CHUNK]->(c)
        SET c.section_id = s.id
        RETURN count(c) as linked_count
        """

        link_result = self.graph.query(link_query, {"doc_id": document_id})
        linked_count = link_result[0]["linked_count"] if link_result else 0

        return {
            "success": True,
            "document_id": document_id,
            "sections_created": len(created_sections),
            "chunks_linked": linked_count,
            "sections": created_sections
        }

    # =========================================================================
    # Integrated Document Graph Processing (M1, M2, M3)
    # =========================================================================

    async def process_document_graph(
        self,
        document_id: str,
        chunks: List[Any],
        options: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Process document chunks and create enriched Graph DB structure.

        Integrates M1, M2, M3 improvements:
        - M1: Entity extraction with confidence filtering
        - M2: Chunk relations (SIMILAR_TO, CO_MENTIONS, OVERLAPS)
        - M3: Section hierarchy from chunk metadata

        Args:
            document_id: Document ID
            chunks: List of TextChunk objects (must have id, content, page_number)
            options: GraphProcessingOptions (optional, uses defaults if None)

        Returns:
            GraphProcessingResult as dict
        """
        import time
        import logging
        from ..models.document import GraphProcessingOptions, GraphProcessingResult

        logger = logging.getLogger(__name__)
        start_time = time.time()

        # Use default options if not provided
        if options is None:
            options = GraphProcessingOptions()

        result = GraphProcessingResult(document_id=document_id)

        try:
            # =================================================================
            # M1: Entity Extraction with Confidence Filtering
            # =================================================================
            if options.extract_entities and chunks:
                logger.info(f"[M1] Starting entity extraction for document {document_id}")

                entity_extractor = EntityExtractor()
                all_entities = []
                batch_size = options.batch_size

                # Process chunks in batches
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i + batch_size]

                    for chunk in batch:
                        chunk_content = getattr(chunk, 'content', str(chunk))
                        chunk_id = getattr(chunk, 'id', f"chunk_{i}")

                        # Extract entities with confidence filtering
                        entities = await entity_extractor.extract_entities_filtered(
                            text=chunk_content[:2000],  # Limit text length
                            apply_threshold=True
                        )

                        # Limit entities per chunk
                        entities = entities[:options.max_entities_per_chunk]
                        result.entities_extracted += len(entities)

                        # Create Entity nodes and MENTIONS relations
                        for entity in entities:
                            await self._create_entity_and_mention(
                                chunk_id=chunk_id,
                                entity=entity,
                                high_threshold=options.high_confidence_threshold
                            )

                            if entity.properties.get("is_high_confidence"):
                                result.high_confidence_entities += 1

                    # Log progress
                    processed = min(i + batch_size, len(chunks))
                    logger.debug(f"[M1] Processed {processed}/{len(chunks)} chunks")

                logger.info(
                    f"[M1] Entity extraction complete: {result.entities_extracted} entities, "
                    f"{result.high_confidence_entities} high-confidence"
                )

            # =================================================================
            # M2: Chunk Relations (SIMILAR_TO, CO_MENTIONS, OVERLAPS)
            # =================================================================
            if options.create_similar_relations:
                logger.info(f"[M2] Creating SIMILAR_TO relations for document {document_id}")
                similar_result = await self.create_chunk_similarity_relations(
                    document_id=document_id,
                    similarity_threshold=options.similarity_threshold
                )
                if similar_result.get("success"):
                    result.similar_relations_created = similar_result.get("created_count", 0)
                logger.info(f"[M2] Created {result.similar_relations_created} SIMILAR_TO relations")

            if options.create_co_mention_relations:
                logger.info(f"[M2] Creating CO_MENTIONS relations for document {document_id}")
                co_mention_result = await self.create_co_mentions_relations(
                    document_id=document_id
                )
                if co_mention_result.get("success"):
                    result.co_mention_relations_created = co_mention_result.get("created_count", 0)
                logger.info(f"[M2] Created {result.co_mention_relations_created} CO_MENTIONS relations")

            if options.create_overlap_relations:
                logger.info(f"[M2] Creating OVERLAPS relations for document {document_id}")
                overlap_result = await self.create_overlap_relations(document_id=document_id)
                if overlap_result.get("success"):
                    result.overlap_relations_created = overlap_result.get("created_count", 0)
                logger.info(f"[M2] Created {result.overlap_relations_created} OVERLAPS relations")

            # =================================================================
            # M3: Section Hierarchy
            # =================================================================
            if options.build_section_hierarchy:
                logger.info(f"[M3] Building section hierarchy for document {document_id}")
                hierarchy_result = await self.build_section_hierarchy_from_chunks(document_id)
                if hierarchy_result.get("success"):
                    result.sections_created = hierarchy_result.get("sections_created", 0)
                    result.section_chunk_links = hierarchy_result.get("chunks_linked", 0)
                logger.info(
                    f"[M3] Section hierarchy complete: {result.sections_created} sections, "
                    f"{result.section_chunk_links} chunk links"
                )

            # Label high-confidence entities (M1)
            if options.extract_entities:
                await self.label_high_confidence_entities(
                    document_id=document_id,
                    threshold=options.high_confidence_threshold
                )

            result.success = True

        except Exception as e:
            logger.error(f"Graph processing failed for document {document_id}: {e}")
            result.success = False
            result.error_message = str(e)

        result.processing_time_seconds = time.time() - start_time
        logger.info(
            f"Graph processing complete for {document_id}: "
            f"success={result.success}, time={result.processing_time_seconds:.2f}s"
        )

        return result.model_dump()

    async def _create_entity_and_mention(
        self,
        chunk_id: str,
        entity: Any,
        high_threshold: float = ENTITY_CONFIDENCE_HIGH
    ) -> bool:
        """
        Create Entity node and MENTIONS relation to Chunk.

        Args:
            chunk_id: Chunk ID
            entity: KGEntity object
            high_threshold: High confidence threshold for labeling

        Returns:
            True if successful
        """
        try:
            # Create or merge Entity node
            entity_labels = "Entity"
            if entity.confidence >= high_threshold:
                entity_labels = "Entity:HighConfidenceEntity"

            query = f"""
            MERGE (e:{entity_labels} {{name: $name}})
            ON CREATE SET
                e.type = $type,
                e.confidence = $confidence,
                e.created_at = datetime()
            ON MATCH SET
                e.confidence = CASE
                    WHEN e.confidence < $confidence THEN $confidence
                    ELSE e.confidence
                END
            WITH e
            MATCH (c:Chunk {{id: $chunk_id}})
            MERGE (c)-[:MENTIONS]->(e)
            RETURN e.name as name
            """

            self.graph.query(query, {
                "name": entity.label,
                "type": entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type),
                "confidence": entity.confidence,
                "chunk_id": chunk_id
            })

            return True
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to create entity {entity.label}: {e}")
            return False


# Factory function
def get_knowledge_graph_service() -> KnowledgeGraphService:
    """Get Knowledge Graph service instance."""
    return KnowledgeGraphService()


def get_chunk_relation_service(graph) -> ChunkRelationService:
    """
    Get Chunk Relation service instance.

    Args:
        graph: Neo4jGraph instance from langchain_neo4j

    Returns:
        ChunkRelationService instance
    """
    return ChunkRelationService(graph)
