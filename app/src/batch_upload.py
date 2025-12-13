#!/usr/bin/env python3
"""
Batch PDF Upload with Semantic Integration
- Concept-based storage with multilingual expressions
- Groups JP/KR documents by semantic meaning
- Enables cross-language RAG queries
"""
import os
import sys
import re
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pypdf import PdfReader
from langchain_openai import ChatOpenAI
from langchain_community.graphs import Neo4jGraph
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Configuration
DOCS_DIR = "/home/ofuser/workspaces/ijswork/graphrag/app/docs"
LLM_URL = "http://localhost:12800/v1"
LLM_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "graphrag2024"

# Processing settings
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
ENTITY_EXTRACTION_INTERVAL = 10
PARALLEL_PDF_LOAD = 5  # Number of PDFs to load in parallel


@dataclass
class PDFDocument:
    """Represents a PDF document with metadata"""
    path: Path
    filename: str
    concept_id: str  # Shared ID for same document in different languages
    language: str    # jp, kr, en
    product: str     # Base, Batch, OSC, etc.
    guide_type: str  # Installation-Guide, User-Guide, etc.
    version: str     # v3.1.2, etc.
    text: str = ""
    pages: int = 0
    is_copy: bool = False


class SemanticBatchUploader:
    """
    Uploads PDFs with semantic integration:

    Graph Schema:
    -------------
    (Concept) - Core semantic unit (e.g., "Base Installation Guide")
        │
        ├── HAS_DOCUMENT → (Document) - Physical PDF file with language
        │                      │
        │                      └── CONTAINS → (Chunk) - Text segments
        │
        └── HAS_EXPRESSION → (Expression) - Language-specific content
                                 │
                                 └── FROM_CHUNK → (Chunk)

    (Entity) - Shared technical terms across languages
        │
        └── MENTIONED_IN → (Chunk)
    """

    def __init__(self):
        print("=" * 70)
        print("  Semantic Batch PDF Upload System")
        print("=" * 70)
        print("\nInitializing...")

        self.llm = ChatOpenAI(
            base_url=LLM_URL,
            model=LLM_MODEL,
            api_key="not-needed",
            temperature=0.1
        )

        self.graph = Neo4jGraph(
            url=NEO4J_URI,
            username=NEO4J_USER,
            password=NEO4J_PASSWORD
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", ".", " ", ""]
        )

        self._init_schema()
        print("Initialization complete.\n")

    def _init_schema(self):
        """Initialize Neo4j schema with constraints and indexes"""
        constraints = [
            "CREATE CONSTRAINT concept_id IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT doc_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE",
            "CREATE CONSTRAINT expr_id IF NOT EXISTS FOR (e:Expression) REQUIRE e.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX chunk_lang IF NOT EXISTS FOR (c:Chunk) ON (c.language)",
            "CREATE INDEX doc_lang IF NOT EXISTS FOR (d:Document) ON (d.language)",
            "CREATE INDEX concept_product IF NOT EXISTS FOR (c:Concept) ON (c.product)",
        ]
        for stmt in constraints + indexes:
            try:
                self.graph.query(stmt)
            except Exception:
                pass

    def _clean_response(self, text: str) -> str:
        """Remove thinking tokens from LLM response"""
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
        return text.strip()

    def parse_filename(self, filepath: Path) -> Optional[PDFDocument]:
        """Parse PDF filename to extract metadata"""
        filename = filepath.name

        # Skip copy files
        if "コピー" in filename or "copy" in filename.lower():
            return PDFDocument(
                path=filepath,
                filename=filename,
                concept_id="",
                language="",
                product="",
                guide_type="",
                version="",
                is_copy=True
            )

        # Pattern: OF_{Product}_{Version}_{Guide}_{DocVersion}_{lang}.pdf
        # Examples:
        #   OF_Base_7.1_Installation-Guide_v3.1.2_jp.pdf
        #   OF_Common_MVS_7.1_Error-Reference-Guide_v3.1.3_JP.pdf
        #   OF_COBOL_4_User-Guide_v2.1.6_ko.pdf

        # Extract language (last part before .pdf)
        lang_match = re.search(r'[_-](jp|kr|ko|JP|KR|KO|en|EN)\.pdf$', filename, re.IGNORECASE)
        if not lang_match:
            return None

        lang = lang_match.group(1).lower()
        if lang == 'ko':
            lang = 'kr'  # Normalize Korean code

        # Remove language suffix to get base name
        base_name = filename[:lang_match.start()]

        # Extract version (vX.X.X pattern)
        version_match = re.search(r'_(v\d+\.\d+\.\d+)', base_name)
        version = version_match.group(1) if version_match else "unknown"

        # Extract product and guide type
        # Pattern: OF_{Product}_{ProductVersion}_{GuideType}_{DocVersion}
        parts = base_name.replace('OF_', '').split('_')

        if len(parts) >= 3:
            # Handle products like "Common_MVS" or "Batch_MVS"
            if 'MVS' in parts:
                mvs_idx = parts.index('MVS')
                product = '_'.join(parts[:mvs_idx + 1])
                remaining = parts[mvs_idx + 1:]
            else:
                product = parts[0]
                remaining = parts[1:]

            # Find guide type (contains "Guide" or "Reference" or "Note")
            guide_parts = []
            for p in remaining:
                if re.match(r'^v\d+', p):
                    break
                if re.match(r'^\d+\.\d+', p):
                    continue
                guide_parts.append(p)
            guide_type = '-'.join(guide_parts) if guide_parts else "Unknown"
        else:
            product = parts[0] if parts else "Unknown"
            guide_type = "Unknown"

        # Generate concept ID (same for all languages of same document)
        concept_base = f"{product}_{guide_type}_{version}".lower()
        concept_base = re.sub(r'[^a-z0-9_-]', '', concept_base)
        concept_id = hashlib.md5(concept_base.encode()).hexdigest()[:12]

        return PDFDocument(
            path=filepath,
            filename=filename,
            concept_id=concept_id,
            language=lang,
            product=product,
            guide_type=guide_type,
            version=version
        )

    def find_all_pdfs(self) -> Dict[str, List[PDFDocument]]:
        """Find all PDFs and group by concept"""
        docs_path = Path(DOCS_DIR)
        if not docs_path.exists():
            print(f"Error: Directory not found: {DOCS_DIR}")
            return {}

        pdfs = list(docs_path.rglob("*.pdf"))

        # Group by concept_id
        concepts = defaultdict(list)
        skipped = []

        for pdf_path in sorted(pdfs):
            doc = self.parse_filename(pdf_path)
            if doc is None:
                skipped.append(pdf_path.name)
                continue
            if doc.is_copy:
                skipped.append(f"{pdf_path.name} (copy)")
                continue
            concepts[doc.concept_id].append(doc)

        print(f"Found {len(pdfs)} PDF files")
        print(f"  -> {len(concepts)} unique concepts")
        print(f"  -> {len(skipped)} skipped (copies or unparseable)")

        return dict(concepts)

    def load_pdf_text(self, doc: PDFDocument) -> PDFDocument:
        """Load PDF and extract text (for parallel processing)"""
        try:
            reader = PdfReader(str(doc.path))
            doc.pages = len(reader.pages)

            all_text = []
            for page in reader.pages:
                try:
                    text = page.extract_text()
                    if text:
                        all_text.append(text)
                except Exception:
                    continue

            doc.text = "\n".join(all_text)
        except Exception as e:
            doc.text = ""
            doc.pages = 0

        return doc

    def load_pdfs_parallel(self, docs: List[PDFDocument]) -> List[PDFDocument]:
        """Load multiple PDFs in parallel"""
        if len(docs) < PARALLEL_PDF_LOAD:
            # Sequential for small batches
            return [self.load_pdf_text(doc) for doc in docs]

        results = []
        with ThreadPoolExecutor(max_workers=PARALLEL_PDF_LOAD) as executor:
            futures = {executor.submit(self.load_pdf_text, doc): doc for doc in docs}
            for future in as_completed(futures):
                results.append(future.result())

        return results

    def extract_entities(self, text: str) -> List[str]:
        """Extract entities from text using LLM"""
        prompt = f"""Extract key technical entities (error codes, commands, system names, API names) from this text.
Return ONLY a comma-separated list. Max 8 items, each under 50 chars.

Text: {text[:500]}

Entities:"""

        try:
            response = self.llm.invoke(prompt)
            entities_str = self._clean_response(response.content)
            entities = [e.strip() for e in entities_str.split(",") if e.strip() and len(e.strip()) < 50]
            return entities[:8]
        except Exception:
            return []

    def clear_graph(self):
        """Clear all existing data from graph"""
        print("Clearing existing graph data...")
        try:
            self.graph.query("MATCH (n) DETACH DELETE n")
            print("Graph cleared.\n")
        except Exception as e:
            print(f"Error clearing graph: {e}\n")

    def process_concept(self, concept_id: str, docs: List[PDFDocument],
                       concept_idx: int, total_concepts: int) -> Dict[str, Any]:
        """Process a concept with all its language variants"""

        # Get representative info from first doc
        sample_doc = docs[0]
        languages = [d.language for d in docs]

        print(f"\n[{concept_idx}/{total_concepts}] Concept: {sample_doc.product} - {sample_doc.guide_type}")
        print(f"  Languages: {', '.join(languages)}")

        # Load all PDFs for this concept in parallel
        print(f"  Loading {len(docs)} PDF(s)...")
        docs = self.load_pdfs_parallel(docs)

        # Filter out failed loads
        valid_docs = [d for d in docs if d.text]
        if not valid_docs:
            print(f"  -> Failed to load any documents")
            return {"status": "failed", "concept_id": concept_id}

        # Create Concept node
        self.graph.query(
            """
            MERGE (c:Concept {id: $concept_id})
            SET c.product = $product,
                c.guide_type = $guide_type,
                c.version = $version,
                c.languages = $languages
            """,
            {
                "concept_id": concept_id,
                "product": sample_doc.product,
                "guide_type": sample_doc.guide_type,
                "version": sample_doc.version,
                "languages": [d.language for d in valid_docs]
            }
        )

        total_chunks = 0
        total_entities = 0

        # Process each language variant
        for doc in valid_docs:
            doc_id = hashlib.md5(f"{doc.filename}:{doc.text[:100]}".encode()).hexdigest()[:12]

            print(f"  Processing [{doc.language.upper()}]: {doc.filename}")
            print(f"    Pages: {doc.pages}, Characters: {len(doc.text):,}")

            # Create Document node
            self.graph.query(
                """
                MERGE (d:Document {id: $doc_id})
                SET d.filename = $filename,
                    d.language = $language,
                    d.pages = $pages,
                    d.type = 'pdf'
                WITH d
                MATCH (c:Concept {id: $concept_id})
                MERGE (c)-[:HAS_DOCUMENT]->(d)
                """,
                {
                    "doc_id": doc_id,
                    "filename": doc.filename,
                    "language": doc.language,
                    "pages": doc.pages,
                    "concept_id": concept_id
                }
            )

            # Split into chunks
            chunks = self.text_splitter.split_text(doc.text)
            print(f"    Chunks: {len(chunks)}")

            # Process chunks
            for i, chunk_text in enumerate(chunks):
                chunk_id = f"{doc_id}_c{i}"

                # Store chunk with language tag
                self.graph.query(
                    """
                    MERGE (ch:Chunk {id: $chunk_id})
                    SET ch.content = $content,
                        ch.index = $index,
                        ch.language = $language
                    WITH ch
                    MATCH (d:Document {id: $doc_id})
                    MERGE (d)-[:CONTAINS]->(ch)
                    """,
                    {
                        "chunk_id": chunk_id,
                        "content": chunk_text,
                        "index": i,
                        "language": doc.language,
                        "doc_id": doc_id
                    }
                )

                # Create Expression node (language-specific content linked to concept)
                expr_id = f"{concept_id}_{doc.language}_e{i}"
                self.graph.query(
                    """
                    MERGE (e:Expression {id: $expr_id})
                    SET e.content = $content,
                        e.language = $language,
                        e.index = $index
                    WITH e
                    MATCH (c:Concept {id: $concept_id})
                    MERGE (c)-[:HAS_EXPRESSION]->(e)
                    WITH e
                    MATCH (ch:Chunk {id: $chunk_id})
                    MERGE (e)-[:FROM_CHUNK]->(ch)
                    """,
                    {
                        "expr_id": expr_id,
                        "content": chunk_text[:500],  # Shortened for expression
                        "language": doc.language,
                        "index": i,
                        "concept_id": concept_id,
                        "chunk_id": chunk_id
                    }
                )

                # Extract entities periodically
                if i % ENTITY_EXTRACTION_INTERVAL == 0:
                    entities = self.extract_entities(chunk_text)
                    for entity in entities:
                        try:
                            self.graph.query(
                                """
                                MERGE (ent:Entity {name: $entity_name})
                                WITH ent
                                MATCH (ch:Chunk {id: $chunk_id})
                                MERGE (ent)-[:MENTIONED_IN]->(ch)
                                """,
                                {"entity_name": entity, "chunk_id": chunk_id}
                            )
                            total_entities += 1
                        except Exception:
                            pass

                total_chunks += 1

            # Progress for large documents
            if len(chunks) > 100:
                print(f"    Completed {len(chunks)} chunks")

        print(f"  -> Concept complete: {total_chunks} chunks, {total_entities} entities")

        return {
            "status": "success",
            "concept_id": concept_id,
            "product": sample_doc.product,
            "guide_type": sample_doc.guide_type,
            "languages": [d.language for d in valid_docs],
            "chunks": total_chunks,
            "entities": total_entities
        }

    def upload_all(self, clear_existing: bool = False) -> Dict[str, Any]:
        """Upload all PDFs organized by concept"""
        if clear_existing:
            self.clear_graph()

        concepts = self.find_all_pdfs()
        if not concepts:
            print("No concepts found.")
            return {"total": 0, "success": 0, "failed": 0}

        print(f"\nProcessing {len(concepts)} concepts...")
        print("-" * 70)

        results = {
            "total_concepts": len(concepts),
            "success": 0,
            "failed": 0,
            "total_chunks": 0,
            "total_entities": 0,
            "details": []
        }

        start_time = time.time()

        for i, (concept_id, docs) in enumerate(concepts.items(), 1):
            result = self.process_concept(concept_id, docs, i, len(concepts))
            results["details"].append(result)

            if result["status"] == "success":
                results["success"] += 1
                results["total_chunks"] += result.get("chunks", 0)
                results["total_entities"] += result.get("entities", 0)
            else:
                results["failed"] += 1

        elapsed = time.time() - start_time

        print("\n" + "=" * 70)
        print("Upload Summary")
        print("=" * 70)
        print(f"Total Concepts:    {results['total_concepts']}")
        print(f"Successful:        {results['success']}")
        print(f"Failed:            {results['failed']}")
        print(f"Total Chunks:      {results['total_chunks']:,}")
        print(f"Total Entities:    {results['total_entities']:,}")
        print(f"Time elapsed:      {elapsed:.1f} seconds")
        print("=" * 70)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Get detailed graph statistics"""
        result = self.graph.query("""
            MATCH (c:Concept) WITH count(c) as concepts
            MATCH (d:Document) WITH concepts, count(d) as docs
            MATCH (ch:Chunk) WITH concepts, docs, count(ch) as chunks
            MATCH (e:Entity) WITH concepts, docs, chunks, count(e) as entities
            MATCH (ex:Expression) WITH concepts, docs, chunks, entities, count(ex) as expressions
            RETURN concepts, docs, chunks, entities, expressions
        """)

        # Language distribution
        lang_dist = self.graph.query("""
            MATCH (d:Document)
            RETURN d.language as language, count(d) as count
            ORDER BY count DESC
        """)

        # Product distribution
        product_dist = self.graph.query("""
            MATCH (c:Concept)
            RETURN c.product as product, count(c) as count
            ORDER BY count DESC
        """)

        stats = {
            "concepts": result[0]["concepts"] if result else 0,
            "documents": result[0]["docs"] if result else 0,
            "chunks": result[0]["chunks"] if result else 0,
            "entities": result[0]["entities"] if result else 0,
            "expressions": result[0]["expressions"] if result else 0,
            "by_language": {r["language"]: r["count"] for r in lang_dist} if lang_dist else {},
            "by_product": {r["product"]: r["count"] for r in product_dist} if product_dist else {}
        }

        return stats

    def search_multilingual(self, keyword: str, preferred_lang: str = None, limit: int = 5) -> List[Dict]:
        """Search across all languages, optionally filtering by preferred language"""

        if preferred_lang:
            # Search in preferred language first, then others
            results = self.graph.query(
                """
                MATCH (ch:Chunk)
                WHERE ch.content CONTAINS $keyword
                OPTIONAL MATCH (ent:Entity)-[:MENTIONED_IN]->(ch)
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(ch)
                OPTIONAL MATCH (c:Concept)-[:HAS_DOCUMENT]->(d)
                WITH ch, d, c, collect(DISTINCT ent.name)[..5] as entities,
                     CASE WHEN ch.language = $lang THEN 0 ELSE 1 END as lang_priority
                ORDER BY lang_priority, ch.index
                RETURN ch.content as content, ch.language as language,
                       d.filename as source, c.product as product,
                       c.guide_type as guide_type, entities
                LIMIT $limit
                """,
                {"keyword": keyword, "lang": preferred_lang, "limit": limit}
            )
        else:
            results = self.graph.query(
                """
                MATCH (ch:Chunk)
                WHERE ch.content CONTAINS $keyword
                OPTIONAL MATCH (ent:Entity)-[:MENTIONED_IN]->(ch)
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(ch)
                OPTIONAL MATCH (c:Concept)-[:HAS_DOCUMENT]->(d)
                RETURN ch.content as content, ch.language as language,
                       d.filename as source, c.product as product,
                       c.guide_type as guide_type,
                       collect(DISTINCT ent.name)[..5] as entities
                LIMIT $limit
                """,
                {"keyword": keyword, "limit": limit}
            )

        return results

    def rag_query(self, question: str, response_lang: str = None) -> str:
        """Perform multilingual RAG query"""

        # Detect question language
        if not response_lang:
            kr_chars = len(re.findall(r'[\uac00-\ud7af]', question))
            jp_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', question))
            if kr_chars > jp_chars:
                response_lang = "kr"
            elif jp_chars > 0:
                response_lang = "jp"
            else:
                response_lang = "en"

        # Extract keywords
        keywords = re.findall(r'[A-Z_]+ERR[A-Z_]*|[A-Z]+-\d+|\w+_\w+_\w+', question)
        if not keywords:
            words = question.split()
            keywords = [w for w in words if len(w) > 2][:5]

        # Search for relevant chunks
        chunks = []
        for keyword in keywords:
            results = self.search_multilingual(keyword, preferred_lang=response_lang, limit=3)
            if results:
                chunks.extend(results)
                break

        if not chunks:
            # Fallback search
            chunks = self.graph.query(
                """
                MATCH (ch:Chunk)
                WHERE ch.language = $lang
                RETURN ch.content as content, ch.language as language
                LIMIT 3
                """,
                {"lang": response_lang}
            )

        # Build context
        context_parts = []
        for chunk in chunks[:5]:
            if chunk.get('content'):
                lang_tag = f"[{chunk.get('language', '?').upper()}]"
                context_parts.append(f"{lang_tag} {chunk['content'][:500]}")

        context = "\n\n".join(context_parts)

        # Generate response
        lang_instruction = {
            "kr": "한국어로 답변하세요.",
            "jp": "日本語で回答してください。",
            "en": "Answer in English."
        }.get(response_lang, "Answer in the same language as the question.")

        prompt = f"""Based on this context, answer the question concisely.
{lang_instruction}

Context:
{context}

Question: {question}

Answer:"""

        response = self.llm.invoke(prompt)
        answer = self._clean_response(response.content)

        # Additional cleaning for thinking patterns
        lines = answer.split('\n')
        clean_lines = [l for l in lines if not re.match(r'^(Okay|First|Let me|Looking|The |I )', l)]
        if clean_lines:
            answer = '\n'.join(clean_lines)

        return answer


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Semantic Batch PDF Upload")
    parser.add_argument("--upload", action="store_true", help="Upload all PDFs")
    parser.add_argument("--clear", action="store_true", help="Clear existing data before upload")
    parser.add_argument("--stats", action="store_true", help="Show graph statistics")
    parser.add_argument("--test", action="store_true", help="Run RAG test queries")
    parser.add_argument("--query", type=str, help="Run a specific RAG query")
    parser.add_argument("--lang", type=str, choices=["kr", "jp", "en"], help="Response language")
    parser.add_argument("--interactive", action="store_true", help="Interactive Q&A mode")

    args = parser.parse_args()

    if not any([args.upload, args.stats, args.test, args.query, args.interactive]):
        args.stats = True
        args.interactive = True

    try:
        uploader = SemanticBatchUploader()

        if args.upload:
            uploader.upload_all(clear_existing=args.clear)

        if args.stats:
            print("\nGraph Statistics:")
            print("-" * 40)
            stats = uploader.get_stats()
            print(f"  Concepts:     {stats['concepts']:,}")
            print(f"  Documents:    {stats['documents']:,}")
            print(f"  Chunks:       {stats['chunks']:,}")
            print(f"  Entities:     {stats['entities']:,}")
            print(f"  Expressions:  {stats['expressions']:,}")

            if stats['by_language']:
                print(f"\n  By Language:")
                for lang, count in stats['by_language'].items():
                    print(f"    {lang}: {count}")

            if stats['by_product']:
                print(f"\n  By Product:")
                for product, count in list(stats['by_product'].items())[:10]:
                    print(f"    {product}: {count}")

        if args.test:
            print("\n" + "=" * 70)
            print("Multilingual RAG Test")
            print("=" * 70)

            test_queries = [
                ("TSAM_ERR_DUPLICATE_KEY 에러의 원인은?", "kr"),
                ("JCL DD文の役割は何ですか?", "jp"),
                ("How to install OpenFrame?", "en"),
                ("COBOL 컴파일 방법", "kr"),
            ]

            for q, lang in test_queries:
                print(f"\nQ [{lang.upper()}]: {q}")
                answer = uploader.rag_query(q, response_lang=lang)
                print(f"A: {answer[:400]}...")
                print("-" * 50)

        if args.query:
            print(f"\nQ: {args.query}")
            answer = uploader.rag_query(args.query, response_lang=args.lang)
            print(f"A: {answer}")

        if args.interactive:
            print("\n" + "=" * 70)
            print("Interactive Multilingual RAG Q&A")
            print("=" * 70)
            print("Commands: 'quit' to exit, 'stats' for statistics")
            print("Tip: Questions in Korean/Japanese get responses in that language")
            print("-" * 70)

            while True:
                try:
                    question = input("\nQ: ").strip()

                    if not question:
                        continue
                    if question.lower() in ['quit', 'exit', 'q']:
                        print("Goodbye!")
                        break
                    if question.lower() == 'stats':
                        stats = uploader.get_stats()
                        print(f"  Concepts: {stats['concepts']}, Documents: {stats['documents']}")
                        print(f"  Chunks: {stats['chunks']}, Entities: {stats['entities']}")
                        continue

                    answer = uploader.rag_query(question, response_lang=args.lang)
                    print(f"\nA: {answer}")
                    print("-" * 50)

                except KeyboardInterrupt:
                    print("\n\nGoodbye!")
                    break

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
