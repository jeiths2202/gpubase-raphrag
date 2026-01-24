"""
Configuration Management for GraphRAG Hybrid System
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """Text LLM (Qwen2.5-7B-Instruct) configuration - GPU 4, port 12800"""
    api_url: str = os.getenv("LLM_API_URL", "http://localhost:12800/v1/chat/completions")
    model: str = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    temperature: float = 0.1


@dataclass
class CodeLLMConfig:
    """Code LLM (CodeQwen 3B) configuration - GPU 7, port 12802"""
    api_url: str = os.getenv("CODE_LLM_API_URL", "http://localhost:12802/v1/chat/completions")
    model: str = os.getenv("CODE_LLM_MODEL", "Qwen/Qwen2.5-Coder-3B-Instruct")
    temperature: float = float(os.getenv("CODE_LLM_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("CODE_LLM_MAX_TOKENS", "2048"))


@dataclass
class VisionLLMConfig:
    """Vision LLM (LLaMA-3.1-Nemotron-Nano-VL) configuration - GPU 6, port 12803"""
    api_url: str = os.getenv("VISION_API_URL", os.getenv("VISION_LLM_API_URL", "http://localhost:12803/v1/chat/completions"))
    model: str = os.getenv("VISION_LLM_MODEL", "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")
    temperature: float = float(os.getenv("VISION_LLM_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("VISION_LLM_MAX_TOKENS", "2048"))


def _build_learning_llm_url() -> str:
    """Build Learning LLM URL from environment variables"""
    url = os.getenv("LEARNING_LLM_URL")
    if url:
        # LEARNING_LLM_URL is base URL like http://host:port/v1
        return f"{url}/chat/completions" if not url.endswith("/chat/completions") else url
    return os.getenv("LEARNING_LLM_API_URL", "http://localhost:12804/v1/chat/completions")


@dataclass
class LearningLLMConfig:
    """Learning LLM (Qwen2.5-7B-AWQ + QLoRA) configuration - GPU 7, port 12804"""
    api_url: str = _build_learning_llm_url()
    model: str = os.getenv("LEARNING_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
    temperature: float = float(os.getenv("LEARNING_LLM_TEMPERATURE", "0.1"))
    max_tokens: int = int(os.getenv("LEARNING_LLM_MAX_TOKENS", "2048"))


@dataclass
class EmbeddingConfig:
    """Embedding NIM configuration"""
    api_url: str = os.getenv("EMBEDDING_API_URL", "http://localhost:12801/v1")
    model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-mistral-7b-v2")
    dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "4096"))
    batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))


@dataclass
class Neo4jConfig:
    """Neo4j database configuration

    SECURITY NOTE:
    - NEO4J_PASSWORD is required with no default value
    - Must be set via environment variable
    """
    uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user: str = os.getenv("NEO4J_USER", "neo4j")
    password: str = os.getenv("NEO4J_PASSWORD", "")  # REQUIRED: Set via environment variable

    def __post_init__(self):
        if not self.password:
            raise ValueError(
                "NEO4J_PASSWORD environment variable is required. "
                "Set a secure password for Neo4j database access."
            )


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

    # Content truncation settings
    content_max_chars: int = int(os.getenv("RAG_CONTENT_MAX_CHARS", "2000"))
    content_preview_chars: int = int(os.getenv("RAG_CONTENT_PREVIEW_CHARS", "500"))

    # Score weight settings for result merging
    topic_density_boost: float = float(os.getenv("RAG_TOPIC_DENSITY_BOOST", "0.1"))
    topic_only_base_score: float = float(os.getenv("RAG_TOPIC_ONLY_BASE_SCORE", "0.3"))
    topic_only_weight: float = float(os.getenv("RAG_TOPIC_ONLY_WEIGHT", "0.2"))


class Config:
    """Central configuration manager"""

    def __init__(self):
        self.llm = LLMConfig()
        self.code_llm = CodeLLMConfig()
        self.vision_llm = VisionLLMConfig()
        self.learning_llm = LearningLLMConfig()
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
