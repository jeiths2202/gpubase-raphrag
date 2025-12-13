"""
Configuration Management for GraphRAG Hybrid System
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """LLM (Nemotron) configuration"""
    api_url: str = os.getenv("LLM_API_URL", "http://localhost:12800/v1/chat/completions")
    model: str = os.getenv("LLM_MODEL", "nvidia/nvidia-nemotron-nano-9b-v2")
    temperature: float = 0.1


@dataclass
class EmbeddingConfig:
    """Embedding NIM configuration"""
    api_url: str = os.getenv("EMBEDDING_API_URL", "http://localhost:12801/v1")
    model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-mistral-7b-v2")
    dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "4096"))
    batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))


@dataclass
class Neo4jConfig:
    """Neo4j database configuration"""
    uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user: str = os.getenv("NEO4J_USER", "neo4j")
    password: str = os.getenv("NEO4J_PASSWORD", "graphrag2024")


@dataclass
class VectorConfig:
    """Vector index configuration"""
    index_name: str = os.getenv("VECTOR_INDEX_NAME", "chunk_embedding")
    similarity_function: str = os.getenv("VECTOR_SIMILARITY_FUNCTION", "cosine")
    dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "4096"))


@dataclass
class RAGConfig:
    """RAG system configuration"""
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "200"))
    default_strategy: str = os.getenv("DEFAULT_RAG_STRATEGY", "auto")
    vector_weight: float = float(os.getenv("VECTOR_WEIGHT", "0.5"))
    top_k: int = int(os.getenv("TOP_K_RESULTS", "5"))


class Config:
    """Central configuration manager"""

    def __init__(self):
        self.llm = LLMConfig()
        self.embedding = EmbeddingConfig()
        self.neo4j = Neo4jConfig()
        self.vector = VectorConfig()
        self.rag = RAGConfig()

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        return cls()


# Global config instance
config = Config.from_env()
