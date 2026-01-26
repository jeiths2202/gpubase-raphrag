"""Configuration for AI Driven RAG System."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from parent directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


class Config:
    """Application configuration."""

    # Neo4j
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")

    # LLM (OpenAI-compatible API)
    llm_api_url: str = os.getenv("LLM_API_URL", "http://localhost:12800/v1")
    llm_model: str = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4096"))

    # Embeddings
    embedding_api_url: str = os.getenv("EMBEDDING_API_URL", "http://localhost:12801/v1")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nv-embedqa-mistral-7b-v2")
    embedding_dimension: int = int(os.getenv("EMBEDDING_DIMENSION", "4096"))

    # Vector Search
    vector_index_name: str = os.getenv("VECTOR_INDEX_NAME", "chunk_embedding_index")
    vector_top_k: int = int(os.getenv("VECTOR_TOP_K", "10"))

    # Agent
    max_tool_calls: int = int(os.getenv("MAX_TOOL_CALLS", "10"))

    # API
    api_host: str = os.getenv("AI_RAG_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("AI_RAG_PORT", "8100"))

    # KMS API (for IMS integration)
    kms_api_url: str = os.getenv("KMS_API_URL", "http://localhost:9000")

    # IMS Crawling (direct authentication)
    ims_base_url: str = os.getenv("IMS_BASE_URL", "https://ims.tmaxsoft.com")
    ims_username: str = os.getenv("IMS_USERNAME", "")
    ims_password: str = os.getenv("IMS_PASSWORD", "")
    ims_product_codes: list[str] = os.getenv(
        "IMS_PRODUCT_CODES",
        "128,520,129,123,500,137,141,126,147,145,135,143,138,134,142,510,127,124,640,425"
    ).split(",")


config = Config()
