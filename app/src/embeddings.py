"""
BGE-M3 Embedding Service for GraphRAG Hybrid System
Supports Dense, Sparse, and Hybrid (Dense+Sparse) embeddings.
"""
import httpx
from typing import List, Dict, Any, Optional
from config import config


class NeMoEmbeddingService:
    """
    Wrapper for BGE-M3 embedding API (OpenAI-compatible + sparse/hybrid).

    Maintains backward compatibility with existing code while adding
    sparse and hybrid encoding capabilities for BGE-M3.
    """

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
        Generate dense embedding for a single text.

        Args:
            text: Text to embed
            input_type: "query" for questions, "passage" for documents

        Returns:
            List of floats representing the 1024-dim dense embedding vector
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
        Generate dense embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            input_type: "query" for questions, "passage" for documents

        Returns:
            List of 1024-dim dense embedding vectors
        """
        embeddings = []

        # Clean texts - remove empty or too short texts
        cleaned_texts = []
        for t in texts:
            if t and len(t.strip()) > 0:
                cleaned_texts.append(t[:8000] if len(t) > 8000 else t)
            else:
                cleaned_texts.append("empty")

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

                batch_embeddings = sorted(data["data"], key=lambda x: x["index"])
                embeddings.extend([item["embedding"] for item in batch_embeddings])

            except Exception as e:
                print(f"  Batch error at {i}: {e}")
                for text in batch:
                    try:
                        emb = self.embed_text(text, input_type)
                        embeddings.append(emb)
                    except Exception:
                        embeddings.append([0.0] * self.dimension)

            if len(cleaned_texts) > self.batch_size and (i + self.batch_size) % 100 == 0:
                print(f"  Embedded {min(i + self.batch_size, len(cleaned_texts))}/{len(cleaned_texts)} texts...")

        return embeddings

    def sparse_encode(self, text: str) -> Dict[str, float]:
        """
        Generate sparse lexical weights for a single text.

        Args:
            text: Text to encode

        Returns:
            Dict mapping token_id (str) to weight (float)
        """
        response = self.client.post(
            f"{self.base_url}/sparse",
            json={"input": text, "model": self.model}
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["sparse_weights"]

    def sparse_encode_batch(self, texts: List[str]) -> List[Dict[str, float]]:
        """
        Generate sparse lexical weights for multiple texts.

        Args:
            texts: List of texts to encode

        Returns:
            List of sparse weight dicts
        """
        response = self.client.post(
            f"{self.base_url}/sparse",
            json={"input": texts, "model": self.model},
            timeout=120.0
        )
        response.raise_for_status()
        data = response.json()
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["sparse_weights"] for item in sorted_data]

    def hybrid_encode(self, text: str) -> Dict[str, Any]:
        """
        Generate both dense and sparse embeddings simultaneously.

        Args:
            text: Text to encode

        Returns:
            Dict with 'dense' (List[float]) and 'sparse' (Dict[str, float])
        """
        response = self.client.post(
            f"{self.base_url}/hybrid",
            json={"input": text, "model": self.model}
        )
        response.raise_for_status()
        data = response.json()
        entry = data["data"][0]
        return {
            "dense": entry["dense"],
            "sparse": entry["sparse_weights"]
        }

    def hybrid_encode_batch(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Generate both dense and sparse embeddings for multiple texts.

        Args:
            texts: List of texts to encode

        Returns:
            List of dicts with 'dense' and 'sparse' keys
        """
        results = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            response = self.client.post(
                f"{self.base_url}/hybrid",
                json={"input": batch, "model": self.model},
                timeout=120.0
            )
            response.raise_for_status()
            data = response.json()
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            for entry in sorted_data:
                results.append({
                    "dense": entry["dense"],
                    "sparse": entry["sparse_weights"]
                })
        return results

    def get_dimension(self) -> int:
        """Return the dense embedding dimension"""
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
    print("Testing BGE-M3 Embedding Service...")

    service = NeMoEmbeddingService()

    if service.health_check():
        print("Service is healthy")

        # Test dense embedding
        test_text = "What is GraphRAG?"
        embedding = service.embed_text(test_text)
        print(f"Dense embedding dimension: {len(embedding)}")

        # Test sparse embedding
        sparse = service.sparse_encode(test_text)
        print(f"Sparse weights: {len(sparse)} non-zero tokens")

        # Test hybrid embedding
        hybrid = service.hybrid_encode(test_text)
        print(f"Hybrid - dense: {len(hybrid['dense'])}-dim, sparse: {len(hybrid['sparse'])} tokens")

        # Test batch
        test_texts = [
            "Neo4j is a graph database",
            "NVIDIA provides GPU acceleration",
            "LangChain is a framework for LLM applications"
        ]
        embeddings = service.embed_batch(test_texts)
        print(f"Batch: {len(embeddings)} vectors of {len(embeddings[0])}-dim")
    else:
        print("Service not available. Ensure BGE-M3 server is running on port 12801")

    service.close()
