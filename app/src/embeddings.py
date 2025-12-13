"""
NeMo Embedding Service for GraphRAG Hybrid System
"""
import httpx
from typing import List, Optional
from config import config


class NeMoEmbeddingService:
    """Wrapper for NeMo Retriever Text Embedding NIM API"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
        timeout: float = 60.0
    ):
        self.base_url = base_url or config.embedding.api_url
        self.model = model or config.embedding.model
        self.batch_size = batch_size or config.embedding.batch_size
        self.dimension = config.embedding.dimension
        self.timeout = timeout
        self._client = None

    @property
    def client(self) -> httpx.Client:
        """Lazy initialization of HTTP client"""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def embed_text(self, text: str, input_type: str = "query") -> List[float]:
        """
        Generate embedding for a single text

        Args:
            text: Text to embed
            input_type: "query" for questions, "passage" for documents

        Returns:
            List of floats representing the embedding vector
        """
        response = self.client.post(
            f"{self.base_url}/embeddings",
            json={
                "model": self.model,
                "input": text,
                "input_type": input_type,
                "encoding_format": "float"
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    def embed_batch(
        self,
        texts: List[str],
        input_type: str = "passage"
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts

        Args:
            texts: List of texts to embed
            input_type: "query" for questions, "passage" for documents

        Returns:
            List of embedding vectors
        """
        embeddings = []

        # Clean texts - remove empty or too short texts
        cleaned_texts = []
        for t in texts:
            if t and len(t.strip()) > 0:
                # Truncate very long texts
                cleaned_texts.append(t[:8000] if len(t) > 8000 else t)
            else:
                cleaned_texts.append("empty")  # Placeholder for empty texts

        # Process in batches
        for i in range(0, len(cleaned_texts), self.batch_size):
            batch = cleaned_texts[i:i + self.batch_size]

            try:
                response = self.client.post(
                    f"{self.base_url}/embeddings",
                    json={
                        "model": self.model,
                        "input": batch,
                        "input_type": input_type,
                        "encoding_format": "float"
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                data = response.json()

                # Sort by index to maintain order
                batch_embeddings = sorted(data["data"], key=lambda x: x["index"])
                embeddings.extend([item["embedding"] for item in batch_embeddings])

            except Exception as e:
                print(f"  Batch error at {i}: {e}")
                # Fall back to single embedding for failed batch
                for text in batch:
                    try:
                        emb = self.embed_text(text, input_type)
                        embeddings.append(emb)
                    except Exception:
                        # Return zero vector for failed texts
                        embeddings.append([0.0] * self.dimension)

            if len(cleaned_texts) > self.batch_size and (i + self.batch_size) % 100 == 0:
                print(f"  Embedded {min(i + self.batch_size, len(cleaned_texts))}/{len(cleaned_texts)} texts...")

        return embeddings

    def get_dimension(self) -> int:
        """Return the embedding dimension"""
        return self.dimension

    def health_check(self) -> bool:
        """Check if the embedding service is available"""
        try:
            response = self.client.get(f"{self.base_url}/health/ready")
            return response.status_code == 200
        except Exception:
            return False

    def close(self):
        """Close the HTTP client"""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Convenience function
def get_embedding_service() -> NeMoEmbeddingService:
    """Get a configured embedding service instance"""
    return NeMoEmbeddingService()


if __name__ == "__main__":
    # Test the embedding service
    print("Testing NeMo Embedding Service...")

    service = NeMoEmbeddingService()

    # Health check
    if service.health_check():
        print("Service is healthy")

        # Test single embedding
        test_text = "What is GraphRAG?"
        embedding = service.embed_text(test_text)
        print(f"Single embedding dimension: {len(embedding)}")

        # Test batch embedding
        test_texts = [
            "Neo4j is a graph database",
            "NVIDIA provides GPU acceleration",
            "LangChain is a framework for LLM applications"
        ]
        embeddings = service.embed_batch(test_texts)
        print(f"Batch embeddings: {len(embeddings)} vectors of dimension {len(embeddings[0])}")
    else:
        print("Service is not available. Make sure NeMo Embedding NIM is running on port 12801")

    service.close()
