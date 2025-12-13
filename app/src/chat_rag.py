"""
Interactive Chat RAG - Command-line chatbot interface for Hybrid RAG
Automatically routes queries to vector, graph, or hybrid strategy
"""
import sys
import io
import os
import re
from typing import Dict, Any, List
from datetime import datetime

# Set UTF-8 encoding environment
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Set UTF-8 encoding for stdin/stdout with error handling
def setup_utf8_encoding():
    """Setup UTF-8 encoding for stdin/stdout safely"""
    try:
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        if hasattr(sys.stdin, 'buffer'):
            sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # Already wrapped or not supported

setup_utf8_encoding()

from hybrid_rag import HybridRAG
from query_router import QueryType


def clean_thinking_tokens(text: str) -> str:
    """Remove LLM thinking tokens from response and normalize whitespace"""
    # Remove complete thinking blocks: <think>...</think>, <thinking>...</thinking>
    text = re.sub(r'<think(?:ing)?>\s*.*?\s*</think(?:ing)?>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove incomplete thinking blocks (opening tag without closing)
    text = re.sub(r'<think(?:ing)?>\s*.*', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove content before closing tag (closing tag without opening)
    text = re.sub(r'^.*?</think(?:ing)?>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Clean up multiple newlines and whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def safe_str(text: str) -> str:
    """Convert text to safe UTF-8 string, replacing invalid characters"""
    if not text:
        return ""
    try:
        # Encode to UTF-8 and decode back, replacing errors
        return text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    except Exception:
        return str(text)


class ChatRAG:
    """Interactive chat interface for Hybrid RAG system"""

    def __init__(self):
        print("=" * 60)
        print("  GraphRAG Interactive Chat")
        print("  Initializing system...")
        print("=" * 60)

        self.rag = HybridRAG()
        self.history: List[Dict] = []

        # Initialize and check status
        status = self.rag.init_system()
        stats = self.rag.get_stats()

        print(f"\n  System Status:")
        for component, ok in status.items():
            icon = "✓" if ok else "✗"
            print(f"    {icon} {component}")

        print(f"\n  Database Statistics:")
        print(f"    Documents: {stats['documents']}")
        print(f"    Chunks: {stats['chunks']}")
        print(f"    Entities: {stats['entities']}")
        print(f"    Embeddings: {stats['embeddings']} ({stats['embedding_coverage']})")

        if not all(status.values()):
            print("\n  [WARNING] Some components are not ready!")

        print("\n" + "=" * 60)
        print("  Commands:")
        print("    /help     - Show help")
        print("    /stats    - Show statistics")
        print("    /history  - Show chat history")
        print("    /clear    - Clear history")
        print("    /quit     - Exit")
        print("=" * 60 + "\n")

    def format_references(self, results: List[Dict]) -> str:
        """Format source references for display"""
        if not results:
            return "  (No references)"

        refs = []
        for i, r in enumerate(results[:5], 1):
            doc_id = r.get("doc_id", "unknown")[:12]
            chunk_idx = r.get("chunk_index", "?")
            score = r.get("score", r.get("combined_score", 0))
            source = r.get("source", "unknown")
            entities = r.get("entities", [])
            content = r.get("content", "")

            # Source badge
            source_badge = {
                "vector": "EMB",
                "graph": "GRAPH",
                "hybrid": "HYBRID"
            }.get(source, source.upper())

            # Content preview (first 80 chars) with encoding safety
            try:
                preview = content[:80].replace("\n", " ").strip()
                # Ensure valid UTF-8
                preview = preview.encode('utf-8', errors='replace').decode('utf-8')
                if len(content) > 80:
                    preview += "..."
            except Exception:
                preview = "(content preview unavailable)"

            ref_line = f"  [{i}] [{source_badge}] Doc:{doc_id} Chunk:#{chunk_idx} Score:{score:.3f}"
            ref_line += f"\n      \"{preview}\""

            if entities:
                ref_line += f"\n      Entities: {', '.join(entities[:5])}"

            refs.append(ref_line)

        return "\n".join(refs)

    def format_strategy_badge(self, strategy: str) -> str:
        """Format strategy indicator"""
        badges = {
            "vector": "[VECTOR/Embedding]",
            "graph": "[GRAPH/Relationship]",
            "hybrid": "[HYBRID/Combined]"
        }
        return badges.get(strategy, f"[{strategy.upper()}]")

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a user query and return formatted result"""
        start_time = datetime.now()

        # Execute query with auto routing
        result = self.rag.query(query, strategy="auto")

        elapsed = (datetime.now() - start_time).total_seconds()

        # Get query classification details
        query_type = self.rag.router.classify_query(query)
        features = self.rag.router.get_query_features(query)

        # Clean thinking tokens from answer and ensure safe encoding
        clean_answer = safe_str(clean_thinking_tokens(result["answer"]))

        # Get document names for references
        results_with_names = self._enrich_results(result.get("results", []))

        return {
            "answer": clean_answer,
            "strategy": result["strategy"],
            "language": result["language"],
            "sources": result["sources"],
            "results": results_with_names,
            "elapsed": elapsed,
            "query_type": query_type.value,
            "features": features
        }

    def _enrich_results(self, results: List[Dict]) -> List[Dict]:
        """Enrich results with document names from Neo4j"""
        if not results:
            return results

        # Get chunk IDs
        chunk_ids = [r.get("chunk_id") for r in results if r.get("chunk_id")]

        if not chunk_ids:
            return results

        try:
            # Query document names
            doc_info = self.rag.graph.query(
                """
                UNWIND $chunk_ids AS cid
                MATCH (d:Document)-[:CONTAINS]->(c:Chunk {id: cid})
                RETURN c.id AS chunk_id, d.id AS doc_id, d.title AS doc_title
                """,
                {"chunk_ids": chunk_ids}
            )

            # Create lookup
            doc_lookup = {r["chunk_id"]: r for r in doc_info}

            # Enrich results
            for r in results:
                cid = r.get("chunk_id")
                if cid in doc_lookup:
                    info = doc_lookup[cid]
                    r["doc_name"] = info.get("doc_title") or info.get("doc_id", "unknown")

        except Exception:
            pass

        return results

    def display_response(self, query: str, response: Dict):
        """Display formatted response"""
        print()
        print("-" * 60)

        # Strategy badge
        strategy_badge = self.format_strategy_badge(response["strategy"])
        print(f"  Strategy: {strategy_badge}")
        print(f"  Language: {response['language']} | Sources: {response['sources']} | Time: {response['elapsed']:.2f}s")
        print("-" * 60)

        # Answer
        print(f"\n{response['answer']}\n")

        # References
        print("-" * 60)
        print("  References:")
        print(self.format_references(response["results"]))
        print("-" * 60)
        print()

    def show_help(self):
        """Show help message"""
        print("""
╔════════════════════════════════════════════════════════════╗
║  GraphRAG Interactive Chat - Help                          ║
╠════════════════════════════════════════════════════════════╣
║  Query Routing:                                            ║
║    - VECTOR: Semantic similarity search (embeddings)       ║
║      Examples: "~이란?", "설명해줘", "방법 알려줘"          ║
║                                                            ║
║    - GRAPH: Relationship/entity traversal                  ║
║      Examples: "A와 B 비교", "목록", "관계 설명"            ║
║                                                            ║
║    - HYBRID: Combined approach                             ║
║      Examples: "원인 분석", "상세히 설명", "이유"           ║
║                                                            ║
║  Commands:                                                 ║
║    /help     - Show this help                              ║
║    /stats    - Show database statistics                    ║
║    /history  - Show conversation history                   ║
║    /clear    - Clear conversation history                  ║
║    /quit     - Exit the chat                               ║
╚════════════════════════════════════════════════════════════╝
""")

    def show_stats(self):
        """Show system statistics"""
        stats = self.rag.get_stats()
        print(f"""
╔════════════════════════════════════════════════════════════╗
║  System Statistics                                         ║
╠════════════════════════════════════════════════════════════╣
║  Documents:     {stats['documents']:<10}                              ║
║  Chunks:        {stats['chunks']:<10}                              ║
║  Entities:      {stats['entities']:<10}                              ║
║  Relationships: {stats['relationships']:<10}                              ║
║  Embeddings:    {stats['embeddings']:<10} ({stats['embedding_coverage']})               ║
╚════════════════════════════════════════════════════════════╝
""")

    def show_history(self):
        """Show conversation history"""
        if not self.history:
            print("\n  (No conversation history)\n")
            return

        print("\n" + "=" * 60)
        print("  Conversation History")
        print("=" * 60)

        for i, item in enumerate(self.history[-10:], 1):
            print(f"\n  [{i}] Q: {item['query'][:50]}...")
            print(f"      Strategy: {item['strategy']} | Sources: {item['sources']}")

        print("\n" + "=" * 60 + "\n")

    def run(self):
        """Main chat loop"""
        print("Ready! Enter your question (or /help for commands)\n")

        while True:
            try:
                # Get user input with safe encoding
                try:
                    raw_input = input("You: ")
                    user_input = safe_str(raw_input).strip()
                except (UnicodeDecodeError, UnicodeEncodeError):
                    print("\n  Input encoding error. Please try again.\n")
                    continue

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    cmd = user_input.lower()

                    if cmd in ["/quit", "/exit", "/q"]:
                        print("\nGoodbye!\n")
                        break
                    elif cmd == "/help":
                        self.show_help()
                    elif cmd == "/stats":
                        self.show_stats()
                    elif cmd == "/history":
                        self.show_history()
                    elif cmd == "/clear":
                        self.history.clear()
                        print("\n  History cleared.\n")
                    else:
                        print(f"\n  Unknown command: {cmd}. Type /help for available commands.\n")
                    continue

                # Process query
                print("\n  Processing...", end="", flush=True)
                response = self.process_query(user_input)
                print("\r" + " " * 20 + "\r", end="")  # Clear "Processing..."

                # Display response
                self.display_response(user_input, response)

                # Save to history
                self.history.append({
                    "query": user_input,
                    "strategy": response["strategy"],
                    "sources": response["sources"],
                    "answer": safe_str(response["answer"][:200])
                })

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type /quit to exit.\n")
            except (UnicodeDecodeError, UnicodeEncodeError) as e:
                print(f"\n  Encoding error: {e}. Try using simpler characters.\n")
            except Exception as e:
                print(f"\n  Error: {e}\n")


def main():
    """Entry point"""
    try:
        chat = ChatRAG()
        chat.run()
    except Exception as e:
        print(f"Failed to initialize: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
