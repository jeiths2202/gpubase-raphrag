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
        language: str = "auto"
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

        # Extract entities
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


# Factory function
def get_knowledge_graph_service() -> KnowledgeGraphService:
    """Get Knowledge Graph service instance."""
    return KnowledgeGraphService()
