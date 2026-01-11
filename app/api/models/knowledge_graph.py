"""
Knowledge Graph Models
지식 그래프 데이터 구조 정의

Based on Neo4j Knowledge Graph concepts:
- Labeled Property Graph (LPG) model
- Ontology-driven schema with inference support
- Entity-Relationship-Property structure
"""
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Entity (Node) types in Knowledge Graph"""
    # Core entity types
    CONCEPT = "concept"           # Abstract concept
    PERSON = "person"             # Person entity
    ORGANIZATION = "organization" # Company, institution
    LOCATION = "location"         # Place, region
    EVENT = "event"               # Time-bound occurrence
    DOCUMENT = "document"         # Source document
    TOPIC = "topic"               # Topic/Theme

    # Technical entity types
    TECHNOLOGY = "technology"     # Technology, tool, framework
    PROCESS = "process"           # Business/technical process
    PRODUCT = "product"           # Product or service
    TERM = "term"                 # Technical term, definition

    # Data entity types
    METRIC = "metric"             # Measurement, KPI
    DATE = "date"                 # Date/time entity
    QUANTITY = "quantity"         # Numeric value with unit


class RelationType(str, Enum):
    """Relationship types between entities"""
    # Hierarchical relationships
    IS_A = "is_a"                     # Type hierarchy (inheritance)
    PART_OF = "part_of"               # Composition
    CONTAINS = "contains"             # Containment
    SUBCLASS_OF = "subclass_of"       # Ontology hierarchy

    # Associative relationships
    RELATED_TO = "related_to"         # General association
    SIMILAR_TO = "similar_to"         # Similarity
    OPPOSITE_OF = "opposite_of"       # Contrast
    SYNONYM_OF = "synonym_of"         # Same meaning

    # Causal relationships
    CAUSES = "causes"                 # Causation
    LEADS_TO = "leads_to"             # Sequence/result
    DEPENDS_ON = "depends_on"         # Dependency
    ENABLES = "enables"               # Enablement
    PREVENTS = "prevents"             # Prevention

    # Temporal relationships
    BEFORE = "before"                 # Temporal order
    AFTER = "after"                   # Temporal order
    DURING = "during"                 # Temporal containment

    # Actor relationships
    CREATED_BY = "created_by"         # Authorship
    OWNED_BY = "owned_by"             # Ownership
    WORKS_FOR = "works_for"           # Employment
    LOCATED_IN = "located_in"         # Location
    PARTICIPATES_IN = "participates_in"  # Participation

    # Knowledge relationships
    DEFINES = "defines"               # Definition
    DESCRIBES = "describes"           # Description
    REFERENCES = "references"         # Citation
    DERIVED_FROM = "derived_from"     # Derivation
    EXAMPLE_OF = "example_of"         # Exemplification

    # Technical relationships
    USES = "uses"                     # Usage
    IMPLEMENTS = "implements"         # Implementation
    EXTENDS = "extends"               # Extension
    INTEGRATES_WITH = "integrates_with"  # Integration


class OntologyClass(BaseModel):
    """Ontology class definition (schema for entity types)"""
    id: str = Field(..., description="Class identifier")
    name: str = Field(..., description="Class name")
    parent_class: Optional[str] = Field(None, description="Parent class for inheritance")
    properties: Dict[str, str] = Field(default_factory=dict, description="Property name -> type mapping")
    description: Optional[str] = Field(None, description="Class description")
    constraints: List[str] = Field(default_factory=list, description="Validation constraints")


class OntologyRelation(BaseModel):
    """Ontology relation definition (schema for relationship types)"""
    id: str = Field(..., description="Relation identifier")
    name: str = Field(..., description="Relation name")
    source_class: str = Field(..., description="Valid source entity class")
    target_class: str = Field(..., description="Valid target entity class")
    properties: Dict[str, str] = Field(default_factory=dict, description="Relation properties")
    inverse: Optional[str] = Field(None, description="Inverse relation name")
    cardinality: str = Field(default="many-to-many", description="Cardinality constraint")


class Ontology(BaseModel):
    """Knowledge Graph Ontology (Schema)"""
    id: str = Field(..., description="Ontology identifier")
    name: str = Field(..., description="Ontology name")
    version: str = Field(default="1.0", description="Ontology version")
    classes: List[OntologyClass] = Field(default_factory=list, description="Entity classes")
    relations: List[OntologyRelation] = Field(default_factory=list, description="Relation definitions")
    prefixes: Dict[str, str] = Field(default_factory=dict, description="Namespace prefixes")
    inference_rules: List[Dict[str, Any]] = Field(default_factory=list, description="Inference rules")


class KGEntity(BaseModel):
    """Knowledge Graph Entity (Node)"""
    id: str = Field(..., description="Entity unique identifier")
    label: str = Field(..., description="Entity display label")
    entity_type: EntityType = Field(..., description="Entity type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Entity properties")

    # Provenance
    source_document_id: Optional[str] = Field(None, description="Source document ID")
    source_chunk_ids: List[str] = Field(default_factory=list, description="Source chunk IDs")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")

    # Ontology reference
    ontology_class: Optional[str] = Field(None, description="Ontology class reference")

    # Metadata
    aliases: List[str] = Field(default_factory=list, description="Alternative names")
    description: Optional[str] = Field(None, description="Entity description")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Visualization
    x: Optional[float] = Field(None, description="X coordinate for visualization")
    y: Optional[float] = Field(None, description="Y coordinate for visualization")
    color: Optional[str] = Field(None, description="Node color")
    size: Optional[float] = Field(None, description="Node size")


class KGRelationship(BaseModel):
    """Knowledge Graph Relationship (Edge)"""
    id: str = Field(..., description="Relationship unique identifier")
    source_id: str = Field(..., description="Source entity ID")
    target_id: str = Field(..., description="Target entity ID")
    relation_type: RelationType = Field(..., description="Relationship type")

    # Properties
    properties: Dict[str, Any] = Field(default_factory=dict, description="Relationship properties")
    label: Optional[str] = Field(None, description="Display label")
    weight: float = Field(default=1.0, ge=0.0, description="Relationship strength/weight")

    # Provenance
    source_document_id: Optional[str] = Field(None, description="Source document ID")
    source_chunk_ids: List[str] = Field(default_factory=list, description="Source chunk IDs")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence")

    # Ontology reference
    ontology_relation: Optional[str] = Field(None, description="Ontology relation reference")

    # Metadata
    bidirectional: bool = Field(default=False, description="Is bidirectional")
    inferred: bool = Field(default=False, description="Was inferred by reasoning")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KnowledgeGraph(BaseModel):
    """Complete Knowledge Graph structure"""
    id: str = Field(..., description="Knowledge Graph ID")
    name: str = Field(..., description="Knowledge Graph name")
    description: Optional[str] = Field(None, description="Description")

    # Graph data
    entities: List[KGEntity] = Field(default_factory=list, description="Entities (nodes)")
    relationships: List[KGRelationship] = Field(default_factory=list, description="Relationships (edges)")

    # Schema
    ontology: Optional[Ontology] = Field(None, description="Knowledge Graph ontology")

    # Statistics
    entity_count: int = Field(default=0, description="Number of entities")
    relationship_count: int = Field(default=0, description="Number of relationships")

    # Source
    source_document_ids: List[str] = Field(default_factory=list, description="Source documents")
    source_query: Optional[str] = Field(None, description="Query that generated this KG")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class KGSummary(BaseModel):
    """Knowledge Graph summary info"""
    id: str
    name: str
    description: Optional[str] = None
    entity_count: int = 0
    relationship_count: int = 0
    entity_types: Dict[str, int] = Field(default_factory=dict, description="Entity type counts")
    relation_types: Dict[str, int] = Field(default_factory=dict, description="Relation type counts")
    created_at: datetime
    updated_at: datetime


# === Request Models ===

class ExtractEntitiesRequest(BaseModel):
    """Request to extract entities from text/query"""
    text: str = Field(..., min_length=1, max_length=10000, description="Text to extract entities from")
    entity_types: List[EntityType] = Field(
        default=[],
        description="Entity types to extract (empty = all types)"
    )
    language: str = Field(default="auto", description="Text language")
    include_embeddings: bool = Field(default=False, description="Include vector embeddings")


class BuildKGRequest(BaseModel):
    """Request to build Knowledge Graph from query/documents"""
    query: Optional[str] = Field(None, description="Query to build KG from")
    document_ids: List[str] = Field(default_factory=list, description="Document IDs to include")
    name: Optional[str] = Field(None, description="Knowledge Graph name")
    description: Optional[str] = Field(None, description="Description")

    # Extraction options
    max_entities: int = Field(default=100, ge=1, le=500, description="Maximum entities to extract")
    max_relationships: int = Field(default=200, ge=1, le=1000, description="Maximum relationships")
    entity_types: List[EntityType] = Field(default_factory=list, description="Entity types to include")
    relation_types: List[RelationType] = Field(default_factory=list, description="Relation types to include")

    # Processing options
    use_llm_extraction: bool = Field(default=True, description="Use LLM for entity/relation extraction")
    use_ner: bool = Field(default=True, description="Use NER for entity detection")
    infer_relationships: bool = Field(default=True, description="Infer implicit relationships")
    merge_similar_entities: bool = Field(default=True, description="Merge similar entities")

    # Language
    language: str = Field(default="auto", description="Language for extraction")


class QueryKGRequest(BaseModel):
    """Request to query Knowledge Graph"""
    knowledge_graph_id: str = Field(..., description="Knowledge Graph ID to query")
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")

    # Query options
    max_hops: int = Field(default=3, ge=1, le=5, description="Maximum graph traversal hops")
    include_paths: bool = Field(default=True, description="Include relationship paths")
    use_embeddings: bool = Field(default=True, description="Use vector similarity")


class ExpandEntityRequest(BaseModel):
    """Request to expand entity with related entities"""
    entity_id: str = Field(..., description="Entity ID to expand")
    max_depth: int = Field(default=2, ge=1, le=4, description="Expansion depth")
    max_neighbors: int = Field(default=20, ge=1, le=50, description="Max neighbors per level")
    relation_types: List[RelationType] = Field(default_factory=list, description="Relation types to follow")


class MergeKGRequest(BaseModel):
    """Request to merge multiple Knowledge Graphs"""
    source_kg_ids: List[str] = Field(..., min_length=2, description="KG IDs to merge")
    name: str = Field(..., description="Name for merged KG")
    description: Optional[str] = Field(None, description="Description")
    merge_strategy: str = Field(
        default="union",
        description="Merge strategy: union, intersection, or overlay"
    )


class InferRelationshipsRequest(BaseModel):
    """Request to infer new relationships using reasoning"""
    knowledge_graph_id: str = Field(..., description="Knowledge Graph ID")
    inference_rules: List[str] = Field(
        default_factory=list,
        description="Specific rules to apply (empty = all applicable rules)"
    )
    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0,
        description="Minimum confidence for inferred relationships"
    )


# === Response Models ===

class ExtractEntitiesResponse(BaseModel):
    """Response from entity extraction"""
    entities: List[KGEntity]
    relationships: List[KGRelationship] = Field(default_factory=list)
    entity_count: int
    relationship_count: int
    processing_time_ms: int


class BuildKGResponse(BaseModel):
    """Response from Knowledge Graph building"""
    knowledge_graph: KnowledgeGraph
    message: str = "Knowledge Graph built successfully"
    stats: Dict[str, Any] = Field(default_factory=dict)


class QueryKGResponse(BaseModel):
    """Response from Knowledge Graph query"""
    answer: str = Field(..., description="Natural language answer")
    relevant_entities: List[KGEntity] = Field(default_factory=list)
    relevant_relationships: List[KGRelationship] = Field(default_factory=list)
    paths: List[List[str]] = Field(default_factory=list, description="Relationship paths found")
    confidence: float = Field(ge=0.0, le=1.0)
    cypher_query: Optional[str] = Field(None, description="Generated Cypher query (if applicable)")


class ExpandEntityResponse(BaseModel):
    """Response from entity expansion"""
    center_entity: KGEntity
    expanded_entities: List[KGEntity]
    relationships: List[KGRelationship]
    depth_reached: int


class InferRelationshipsResponse(BaseModel):
    """Response from relationship inference"""
    inferred_relationships: List[KGRelationship]
    rules_applied: List[str]
    inference_count: int


class KGListResponse(BaseModel):
    """List of Knowledge Graphs"""
    knowledge_graphs: List[KGSummary]
    total: int


# === Cypher Query Models ===

class CypherQueryRequest(BaseModel):
    """Request to execute Cypher query on Knowledge Graph"""
    knowledge_graph_id: str = Field(..., description="Knowledge Graph ID")
    cypher: str = Field(..., description="Cypher query to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Query parameters")


class CypherQueryResponse(BaseModel):
    """Response from Cypher query execution"""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0


# === Neo4j Export Models ===

class Neo4jExportRequest(BaseModel):
    """Request to export Knowledge Graph to Neo4j format"""
    knowledge_graph_id: str = Field(..., description="Knowledge Graph ID to export")
    format: str = Field(
        default="cypher",
        description="Export format: cypher, json, or graphml"
    )
    include_properties: bool = Field(default=True, description="Include all properties")


class Neo4jExportResponse(BaseModel):
    """Response with Neo4j export data"""
    format: str
    data: str = Field(..., description="Export data in requested format")
    node_count: int
    relationship_count: int
