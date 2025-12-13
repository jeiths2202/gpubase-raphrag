"""
Hybrid RAG Module for GraphRAG System
Orchestrates Vector RAG and Graph RAG based on query classification
"""
import re
from typing import List, Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph
from config import config
from embeddings import NeMoEmbeddingService
from query_router import QueryRouter, QueryType
from vector_rag import VectorRAG


class HybridRAG:
    """
    Hybrid RAG system combining Vector and Graph-based retrieval

    - Automatically routes queries to appropriate strategy
    - Merges and reranks results from multiple sources
    - Generates unified responses
    """

    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        llm_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        embedding_url: Optional[str] = None
    ):
        """
        Initialize HybridRAG system

        Args:
            neo4j_uri: Neo4j connection URI
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            llm_url: LLM API URL
            llm_model: LLM model name
            embedding_url: Embedding API URL
        """
        # Neo4j connection
        self.graph = Neo4jGraph(
            url=neo4j_uri or config.neo4j.uri,
            username=neo4j_user or config.neo4j.user,
            password=neo4j_password or config.neo4j.password
        )

        # LLM (Nemotron for RAG)
        self.llm = ChatOpenAI(
            base_url=(llm_url or config.llm.api_url).replace("/chat/completions", ""),
            model=llm_model or config.llm.model,
            api_key="not-needed",
            temperature=0.1
        )

        # Code LLM (Mistral NeMo for code generation/analysis)
        self.code_llm = ChatOpenAI(
            base_url=config.code_llm.api_url.replace("/chat/completions", ""),
            model=config.code_llm.model,
            api_key="not-needed",
            temperature=config.code_llm.temperature,
            max_tokens=config.code_llm.max_tokens
        )

        # Embedding service
        self.embedding_service = NeMoEmbeddingService(
            base_url=embedding_url or config.embedding.api_url
        )

        # Query router
        self.router = QueryRouter(self.llm)

        # Vector RAG
        self.vector_rag = VectorRAG(
            graph=self.graph,
            embedding_service=self.embedding_service,
            llm=self.llm
        )

        # Configuration
        self.vector_weight = config.rag.vector_weight
        self.top_k = config.rag.top_k

    def query(
        self,
        question: str,
        strategy: str = "auto",
        language: str = "auto",
        k: int = None,
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Answer a question using hybrid RAG

        Args:
            question: The user's question
            strategy: RAG strategy (auto, vector, graph, hybrid)
            language: Response language (auto, ko, ja, en)
            k: Number of results to retrieve
            conversation_history: List of previous Q&A pairs for context

        Returns:
            Dictionary with answer and metadata
        """
        # Detect if query needs comprehensive answer (listing multiple items)
        is_comprehensive = self._is_comprehensive_query(question)

        # Detect if query needs deep analysis (detailed, thorough response)
        is_deep_analysis = self._is_deep_analysis_query(question)

        # Adjust k based on query type
        if k is None:
            if is_deep_analysis:
                k = self.top_k * 4  # 20 results for deep analysis
            elif is_comprehensive:
                k = self.top_k * 2  # 10 results for comprehensive
            else:
                k = self.top_k      # 5 results for normal

        # Detect language if auto
        if language == "auto":
            language = self._detect_language(question)

        # Determine strategy
        if strategy == "auto":
            query_type = self.router.classify_query(question)
            strategy = query_type.value

        # Handle CODE strategy separately (direct to Code LLM)
        if strategy == "code":
            answer = self._generate_code_response(question, language, conversation_history)
            return {
                "answer": answer,
                "strategy": strategy,
                "language": language,
                "sources": 0,  # No RAG sources for code generation
                "results": []
            }

        # Execute appropriate RAG strategy
        if strategy == "vector":
            results = self._vector_search(question, k)
        elif strategy == "graph":
            results = self._graph_search(question, k)
        else:  # hybrid
            results = self._hybrid_search(question, k)

        # Generate answer with conversation context
        answer = self._generate_answer(
            question, results, language,
            conversation_history=conversation_history,
            is_comprehensive=is_comprehensive,
            is_deep_analysis=is_deep_analysis
        )

        return {
            "answer": answer,
            "strategy": strategy,
            "language": language,
            "sources": len(results),
            "results": results[:3]  # Top 3 for reference
        }

    def _vector_search(self, query: str, k: int) -> List[Dict]:
        """Execute vector similarity search with topic density boosting"""
        # Extract key concept and search by topic density
        key_concept = self._extract_key_concept(query)
        topic_density_results = []
        if key_concept:
            print(f"    [Topic Density] Key concept: '{key_concept}'")
            topic_density_results = self._search_by_topic_density(key_concept, k)
            if topic_density_results:
                print(f"    [Topic Density] Found {len(topic_density_results)} results from topic-central documents")

        # Get vector search results
        vector_results = self.vector_rag.search_similar(query, k=k)

        # Merge topic density and vector results
        if topic_density_results:
            merged = self._merge_topic_density_with_vector(topic_density_results, vector_results)
            return merged[:k]

        return vector_results

    def _merge_topic_density_with_vector(
        self,
        topic_density_results: List[Dict],
        vector_results: List[Dict]
    ) -> List[Dict]:
        """Merge topic density results with vector results for VECTOR strategy"""
        seen_chunks = set()
        merged = []

        # Topic density results first (concept-central documents)
        for result in topic_density_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                topic_score = result.get("topic_density", 0.5)
                result["combined_score"] = 0.85 + (topic_score * 0.15)  # 0.85 ~ 1.0 range
                result["source"] = "topic_density"
                merged.append(result)
                seen_chunks.add(chunk_id)

        # Vector results (with similarity scores)
        for result in vector_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                result["combined_score"] = result["score"] * 0.8  # Slightly lower priority
                merged.append(result)
                seen_chunks.add(chunk_id)
            else:
                # Boost if also found by vector
                for m in merged:
                    if m["chunk_id"] == chunk_id:
                        m["combined_score"] += result["score"] * 0.15
                        m["source"] = "topic_density_vector"
                        break

        # Sort by combined score
        return sorted(merged, key=lambda x: x.get("combined_score", 0), reverse=True)

    def _graph_search(self, query: str, k: int) -> List[Dict]:
        """Execute graph-based search with entity traversal"""
        # Extract keywords for search
        keywords = self._extract_keywords(query)

        if not keywords:
            # Fallback to simple content search
            results = self.graph.query(
                """
                MATCH (c:Chunk)
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                RETURN
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    d.id AS doc_id,
                    collect(DISTINCT e.name)[..5] AS entities
                ORDER BY c.index
                LIMIT $k
                """,
                {"k": k}
            )
        else:
            # First try: Search entities that match keywords
            entity_results = self.graph.query(
                """
                UNWIND $keywords AS keyword
                MATCH (e:Entity)
                WHERE toLower(e.name) CONTAINS toLower(keyword)
                MATCH (c:Chunk)-[:MENTIONS]->(e)
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                WITH c, d, collect(DISTINCT e.name)[..5] AS entities, count(e) AS match_count
                RETURN DISTINCT
                    c.id AS chunk_id,
                    c.content AS content,
                    c.index AS chunk_index,
                    d.id AS doc_id,
                    entities,
                    match_count
                ORDER BY match_count DESC, c.index
                LIMIT $k
                """,
                {"keywords": keywords, "k": k}
            )

            # If entity search found results, use them
            if entity_results:
                results = entity_results
            else:
                # Fallback: Search content with case-insensitive match
                keyword = keywords[0]
                results = self.graph.query(
                    """
                    MATCH (c:Chunk)
                    WHERE toLower(c.content) CONTAINS toLower($keyword)
                    OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                    OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                    WITH c, d, collect(DISTINCT e.name)[..5] AS entities
                    RETURN
                        c.id AS chunk_id,
                        c.content AS content,
                        c.index AS chunk_index,
                        d.id AS doc_id,
                        entities
                    ORDER BY c.index
                    LIMIT $k
                    """,
                    {"keyword": keyword, "k": k}
                )

        return [
            {
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "chunk_index": r["chunk_index"],
                "doc_id": r["doc_id"],
                "entities": r["entities"] or [],
                "score": r.get("match_count", 1.0),  # Use match count as score
                "source": "graph"
            }
            for r in results
        ]

    def _hybrid_search(self, query: str, k: int) -> List[Dict]:
        """Execute both vector and graph search, merge results"""
        # Check for numeric error codes (e.g., -5212)
        error_code_results = self._search_numeric_error_code(query, k)

        # Extract key concept and search by topic density (Option 1+3)
        key_concept = self._extract_key_concept(query)
        topic_density_results = []
        if key_concept:
            print(f"    [Topic Density] Key concept: '{key_concept}'")
            topic_density_results = self._search_by_topic_density(key_concept, k)
            if topic_density_results:
                print(f"    [Topic Density] Found {len(topic_density_results)} results from topic-central documents")

        # Get results from both sources
        vector_results = self._vector_search(query, k)
        graph_results = self._graph_search(query, k)

        # Merge and deduplicate
        # Priority: error_code > topic_density > vector/graph hybrid
        merged = self._merge_results_with_topic_density(
            vector_results, graph_results, error_code_results, topic_density_results
        )

        # Rerank
        reranked = self._rerank_results(merged, query)

        return reranked[:k]

    def _search_numeric_error_code(self, query: str, k: int) -> List[Dict]:
        """Search for numeric error codes like -5212 directly in content"""
        # Find numeric error codes in query
        error_codes = re.findall(r'-\d{3,5}', query)

        if not error_codes:
            return []

        results = []
        for error_code in error_codes:
            # Direct content search for the error code
            search_results = self.graph.query(
                """
                MATCH (c:Chunk)
                WHERE c.content CONTAINS $error_code
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                OPTIONAL MATCH (d:Document)-[:CONTAINS]->(c)
                RETURN
                    c.id AS chunk_id,
                    c.content AS content,
                    d.id AS doc_id,
                    collect(DISTINCT e.name)[..5] AS entities
                LIMIT $k
                """,
                {"error_code": error_code, "k": k}
            )

            for r in search_results:
                results.append({
                    "chunk_id": r["chunk_id"],
                    "content": r["content"],
                    "chunk_index": None,
                    "doc_id": r["doc_id"],
                    "entities": r["entities"] or [],
                    "score": 1.0,  # High score for exact match
                    "source": "error_code"
                })

        return results

    def _merge_results(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
        error_code_results: List[Dict] = None
    ) -> List[Dict]:
        """Merge results from vector, graph, and error code search"""
        seen_chunks = set()
        merged = []

        # Process error code results first (highest priority)
        if error_code_results:
            for result in error_code_results:
                chunk_id = result["chunk_id"]
                if chunk_id not in seen_chunks:
                    result["combined_score"] = 1.0  # Highest priority
                    merged.append(result)
                    seen_chunks.add(chunk_id)

        # Process vector results (with similarity scores)
        for result in vector_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                result["combined_score"] = result["score"] * self.vector_weight
                merged.append(result)
                seen_chunks.add(chunk_id)

        # Process graph results
        graph_weight = 1.0 - self.vector_weight
        for result in graph_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                result["combined_score"] = result.get("score", 0.5) * graph_weight
                merged.append(result)
                seen_chunks.add(chunk_id)
            else:
                # Boost score for chunks found by both methods
                for m in merged:
                    if m["chunk_id"] == chunk_id:
                        m["combined_score"] += result.get("score", 0.5) * graph_weight
                        m["source"] = "hybrid"
                        break

        return merged

    def _merge_results_with_topic_density(
        self,
        vector_results: List[Dict],
        graph_results: List[Dict],
        error_code_results: List[Dict] = None,
        topic_density_results: List[Dict] = None
    ) -> List[Dict]:
        """
        Merge results with topic density prioritization

        Priority order:
        1. Error code results (exact match, highest priority)
        2. Topic density results (documents where concept is central)
        3. Vector + Graph hybrid results
        """
        seen_chunks = set()
        merged = []

        # 1. Process error code results first (highest priority)
        if error_code_results:
            for result in error_code_results:
                chunk_id = result["chunk_id"]
                if chunk_id not in seen_chunks:
                    result["combined_score"] = 1.0  # Highest priority
                    merged.append(result)
                    seen_chunks.add(chunk_id)

        # 2. Process topic density results (concept-central documents)
        if topic_density_results:
            for result in topic_density_results:
                chunk_id = result["chunk_id"]
                if chunk_id not in seen_chunks:
                    # Score based on topic density (0.0 to 1.0) + base boost
                    topic_score = result.get("topic_density", 0.5)
                    result["combined_score"] = 0.9 + (topic_score * 0.1)  # 0.9 ~ 1.0 range
                    merged.append(result)
                    seen_chunks.add(chunk_id)
                else:
                    # Boost existing chunk if also found by topic density
                    for m in merged:
                        if m["chunk_id"] == chunk_id:
                            m["combined_score"] += 0.2  # Boost
                            m["source"] = "topic_density_boosted"
                            break

        # 3. Process vector results
        for result in vector_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                result["combined_score"] = result["score"] * self.vector_weight * 0.8  # Slightly lower priority
                merged.append(result)
                seen_chunks.add(chunk_id)
            else:
                # Boost if also found by vector
                for m in merged:
                    if m["chunk_id"] == chunk_id:
                        m["combined_score"] += result["score"] * 0.1
                        break

        # 4. Process graph results
        graph_weight = 1.0 - self.vector_weight
        for result in graph_results:
            chunk_id = result["chunk_id"]
            if chunk_id not in seen_chunks:
                result["combined_score"] = result.get("score", 0.5) * graph_weight * 0.8
                merged.append(result)
                seen_chunks.add(chunk_id)
            else:
                # Boost if also found by graph
                for m in merged:
                    if m["chunk_id"] == chunk_id:
                        m["combined_score"] += result.get("score", 0.5) * 0.1
                        if "hybrid" not in m.get("source", ""):
                            m["source"] = m.get("source", "") + "_hybrid"
                        break

        return merged

    def _rerank_results(self, results: List[Dict], query: str) -> List[Dict]:
        """Rerank merged results"""
        # Sort by combined score
        sorted_results = sorted(
            results,
            key=lambda x: x.get("combined_score", 0),
            reverse=True
        )

        # Boost results with query keywords in content
        keywords = self._extract_keywords(query)
        for result in sorted_results:
            content_lower = result["content"].lower()
            keyword_matches = sum(1 for kw in keywords if kw.lower() in content_lower)
            if keyword_matches > 0:
                result["combined_score"] *= (1 + 0.1 * keyword_matches)

        # Re-sort after boosting
        return sorted(sorted_results, key=lambda x: x.get("combined_score", 0), reverse=True)

    def _generate_answer(
        self,
        question: str,
        results: List[Dict],
        language: str,
        conversation_history: List[Dict] = None,
        is_comprehensive: bool = False,
        is_deep_analysis: bool = False
    ) -> str:
        """Generate answer using LLM with optional conversation context"""
        if not results:
            return self._no_results_message(language)

        # Adjust context size based on query type
        if is_deep_analysis:
            max_results = 20
            max_content_length = 1500  # Much more content for deep analysis
        elif is_comprehensive:
            max_results = 10
            max_content_length = 800
        else:
            max_results = 5
            max_content_length = 500

        # Build document context
        context_parts = []
        for i, r in enumerate(results[:max_results], 1):
            content = r["content"][:max_content_length]
            context_parts.append(f"[{i}] {content}")
            if r.get("entities"):
                context_parts.append(f"    Related entities: {', '.join(r['entities'])}")

        context = "\n\n".join(context_parts)

        # Language instruction
        lang_instruction = self._get_language_instruction(language)

        # Build conversation history section
        conversation_context = ""
        if conversation_history:
            # Limit to last 3 turns to avoid token overflow
            recent_history = conversation_history[-3:]
            history_parts = []
            for turn in recent_history:
                q = turn.get("query", "")[:200]
                a = turn.get("answer", "")[:300]
                history_parts.append(f"User: {q}\nAssistant: {a}")

            if history_parts:
                conversation_context = f"""
Previous conversation:
{chr(10).join(history_parts)}

"""

        # Comprehensive instruction for list-type queries
        comprehensive_instruction = ""
        if is_comprehensive:
            if language == "ko":
                comprehensive_instruction = "\n중요: 문서에서 찾은 모든 관련 항목을 빠짐없이 나열해주세요. 하나만 언급하지 말고 전체 목록을 제공하세요.\n"
            elif language == "ja":
                comprehensive_instruction = "\n重要: ドキュメントで見つかったすべての関連項目を漏れなくリストアップしてください。\n"
            else:
                comprehensive_instruction = "\nIMPORTANT: List ALL relevant items found in the documents. Do not mention just one item if there are multiple.\n"

        # Deep analysis instruction for thorough, detailed responses
        deep_analysis_instruction = ""
        if is_deep_analysis:
            if language == "ko":
                deep_analysis_instruction = """
[심층 분석 모드]
사용자가 자세하고 깊이 있는 분석을 요청했습니다. 다음 지침을 따라주세요:
1. 제공된 모든 문서를 철저히 분석하세요
2. 관련된 모든 정보를 빠짐없이 포함하세요
3. 개념, 원인, 해결방법, 예시 등을 상세하게 설명하세요
4. 가능한 한 구체적이고 실용적인 정보를 제공하세요
5. 관련 배경 정보와 맥락도 함께 설명하세요
6. 길고 상세한 답변을 제공하세요 - 간략하게 답하지 마세요

"""
            elif language == "ja":
                deep_analysis_instruction = """
[深層分析モード]
ユーザーが詳細で深い分析を要求しています。以下の指針に従ってください：
1. 提供されたすべてのドキュメントを徹底的に分析してください
2. 関連するすべての情報を漏れなく含めてください
3. 概念、原因、解決方法、例などを詳しく説明してください
4. できるだけ具体的で実用的な情報を提供してください
5. 関連する背景情報とコンテキストも一緒に説明してください
6. 長く詳細な回答を提供してください - 簡潔に答えないでください

"""
            else:
                deep_analysis_instruction = """
[DEEP ANALYSIS MODE]
The user has requested a detailed, thorough analysis. Follow these guidelines:
1. Thoroughly analyze ALL provided documents
2. Include ALL relevant information without omission
3. Explain concepts, causes, solutions, and examples in detail
4. Provide specific and practical information
5. Include related background information and context
6. Provide a long, detailed response - do NOT be brief

"""

        # Generate answer with conversation context
        prompt = f"""Based on the context below, answer the question.
{lang_instruction}{comprehensive_instruction}{deep_analysis_instruction}
{conversation_context}Document Context:
{context}

Current Question: {question}

Answer (consider the previous conversation if relevant):"""

        response = self.llm.invoke(prompt)
        answer = response.content

        # Clean thinking tokens
        answer = self._clean_response(answer)

        return answer

    def _generate_code_response(
        self,
        question: str,
        language: str,
        conversation_history: List[Dict] = None
    ) -> str:
        """
        Generate code response using Code LLM (Mistral NeMo)

        Args:
            question: The user's question (code-related)
            language: Response language (ko, ja, en)
            conversation_history: Previous Q&A pairs

        Returns:
            Generated code or code analysis
        """
        # Build conversation context
        conversation_context = ""
        if conversation_history:
            recent_history = conversation_history[-3:]
            history_parts = []
            for turn in recent_history:
                q = turn.get("query", "")[:200]
                a = turn.get("answer", "")[:300]
                history_parts.append(f"User: {q}\nAssistant: {a}")

            if history_parts:
                conversation_context = f"""
Previous conversation:
{chr(10).join(history_parts)}

"""

        # Language instruction for response
        lang_instruction = ""
        if language == "ko":
            lang_instruction = "Please respond in Korean. Provide explanations in Korean but keep code comments in English for readability.\n"
        elif language == "ja":
            lang_instruction = "日本語で回答してください。説明は日本語で、コードコメントは可読性のため英語で記述してください。\n"

        # Build prompt for code generation
        prompt = f"""{lang_instruction}{conversation_context}You are an expert programmer. Help the user with their code-related request.

User Request: {question}

Provide:
1. Clear, well-commented code
2. Brief explanation of how it works
3. Usage examples if applicable

Response:"""

        try:
            response = self.code_llm.invoke(prompt)
            answer = response.content

            # Clean thinking tokens if any
            answer = self._clean_response(answer)

            return answer

        except Exception as e:
            error_msg = {
                "ko": f"코드 생성 중 오류가 발생했습니다: {e}",
                "ja": f"コード生成中にエラーが発生しました: {e}",
                "en": f"Error generating code: {e}"
            }
            return error_msg.get(language, error_msg["en"])

    def _extract_key_concept(self, query: str) -> str:
        """
        Extract the central/key concept from a query using LLM

        This helps identify the main topic to prioritize documents
        where that topic is central, not just mentioned.

        Args:
            query: User's query

        Returns:
            The key concept/keyword that is most central to the query
        """
        prompt = f"""다음 질문에서 핵심 주제/동작을 나타내는 키워드 1개만 추출하세요.

규칙:
- 주요 동작/프로세스 단어를 우선 선택 (예: 마이그레이션, 변환, 설치, 설정)
- 대상 명사보다 행위/과정을 나타내는 단어를 선택
- 조사(을/를/이/가/의/에서/으로)는 제외하고 단어만 반환
- 영어 단어도 가능

질문: {query}

핵심 키워드(한 단어만):"""

        # First try fallback for common action words (faster and more reliable)
        fallback_concept = self._fallback_key_concept(query)

        try:
            response = self.llm.invoke(prompt)
            concept = response.content.strip()

            # Clean up - remove quotes, periods, particles, etc.
            concept = re.sub(r'["\'.。、:：]', '', concept)
            concept = concept.split('\n')[0].strip()  # Take first line only
            concept = concept.split()[0] if concept.split() else concept  # Take first word only

            # Remove Korean particles if present
            concept = re.sub(r'(을|를|이|가|의|에서|으로|에|와|과|도|만)$', '', concept)

            # Validate: concept should be in the original query
            if concept and len(concept) >= 2:
                # Check if concept is in query (with or without particles)
                if concept.lower() in query.lower():
                    # Prefer action words from fallback if LLM returned something else
                    if fallback_concept and fallback_concept != concept:
                        # Check if fallback found an action word
                        action_words = {'마이그레이션', '변환', '이동', '전환', '이관',
                                       '설치', '설정', '구성', '배포', '실행',
                                       '에러', '오류', '해결', 'migration', 'error'}
                        if fallback_concept.lower() in action_words or any(aw in fallback_concept.lower() for aw in action_words):
                            return fallback_concept
                    return concept
                # Also try without potential particle at the end
                for suffix in ['을', '를', '이', '가', '의', '에서', '으로', '에', '하는', '한']:
                    if (concept + suffix).lower() in query.lower():
                        return concept

            # Return fallback result
            return fallback_concept

        except Exception as e:
            print(f"Key concept extraction error: {e}")
            return fallback_concept

    def _fallback_key_concept(self, query: str) -> str:
        """Fallback key concept extraction using simple heuristics"""
        # Priority action/process words (these are likely the central topic)
        action_patterns = [
            r'마이그레이션', r'변환', r'이동', r'전환', r'이관',
            r'설치', r'설정', r'구성', r'배포', r'실행',
            r'생성', r'삭제', r'수정', r'업데이트', r'업그레이드',
            r'migration', r'convert', r'install', r'setup', r'deploy',
            r'에러', r'오류', r'error', r'해결', r'처리'
        ]

        # First, check for action words
        for pattern in action_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                match = re.search(pattern, query, re.IGNORECASE)
                return match.group()

        # Remove common question/filler words
        stop_words = {
            '방법', '하는', '에서', '으로', '대해', '대해서', '알려', '주세요',
            '무엇', '어떻게', '왜', '언제', 'what', 'how', 'why', 'when',
            '상세', '자세', '하게', '히', '을', '를', '이', '가', '의',
            '데이터셋을', '데이터셋으로', '데이터셋'
        }

        # Split into words and find meaningful ones
        words = re.findall(r'[A-Za-z가-힣]+', query)
        meaningful = [w for w in words if len(w) >= 2 and w.lower() not in stop_words]

        if meaningful:
            # Return the longest meaningful word (likely the key concept)
            return max(meaningful, key=len)

        return ""

    def _search_by_topic_density(self, concept: str, k: int) -> List[Dict]:
        """
        Search documents where the concept is central (high topic density)

        Topic density = number of chunks containing concept / total chunks in document
        Documents with higher density have the concept as a more central topic.

        Args:
            concept: The key concept to search for
            k: Number of results to return

        Returns:
            List of chunks from documents where the concept is most central
        """
        if not concept:
            return []

        # Find documents and score by topic density
        results = self.graph.query(
            """
            // First, find all documents containing the concept
            MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
            WHERE c.content CONTAINS $concept
            WITH d, count(c) AS concept_chunks

            // Get total chunks per document
            MATCH (d)-[:CONTAINS]->(all_chunks:Chunk)
            WITH d, concept_chunks, count(all_chunks) AS total_chunks

            // Calculate topic density
            WITH d, concept_chunks, total_chunks,
                 toFloat(concept_chunks) / toFloat(total_chunks) AS topic_density

            // Order by density (concept centrality) then by absolute count
            ORDER BY topic_density DESC, concept_chunks DESC

            // Get chunks from top documents
            MATCH (d)-[:CONTAINS]->(c:Chunk)
            WHERE c.content CONTAINS $concept
            OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)

            RETURN
                c.id AS chunk_id,
                c.content AS content,
                c.index AS chunk_index,
                d.id AS doc_id,
                collect(DISTINCT e.name)[..5] AS entities,
                topic_density,
                concept_chunks AS doc_concept_count
            ORDER BY topic_density DESC, c.index
            LIMIT $k
            """,
            {"concept": concept, "k": k}
        )

        return [
            {
                "chunk_id": r["chunk_id"],
                "content": r["content"],
                "chunk_index": r["chunk_index"],
                "doc_id": r["doc_id"],
                "entities": r["entities"] or [],
                "score": r["topic_density"],  # Use topic density as score
                "topic_density": r["topic_density"],
                "doc_concept_count": r["doc_concept_count"],
                "source": "topic_density"
            }
            for r in results
        ]

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text"""
        keywords = []

        # Error codes (high priority)
        error_codes = re.findall(r'[A-Z_]+ERR[A-Z_]*|[A-Z]+-\d+', text)
        keywords.extend(error_codes)

        # Product/technical names (OF*, Open*, etc.)
        product_names = re.findall(r'\b(?:OF[A-Za-z]+|Open[A-Za-z]+|OFCOBOL|OFASM|PROSORT|JEUS|Tibero|Neo4j)\b', text, re.IGNORECASE)
        keywords.extend(product_names)

        # Technical terms (capitalized words like GraphRAG, Neo4j)
        tech_terms = re.findall(r'\b[A-Z][a-zA-Z]*[A-Z][a-zA-Z]*\b', text)
        keywords.extend(tech_terms)

        # Korean comparison patterns: "A와 B", "A과 B"
        korean_compare = re.findall(r'([A-Za-z가-힣]+)[와과]\s*([A-Za-z가-힣]+)', text)
        for match in korean_compare:
            keywords.extend(match)

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen and len(kw) >= 2:
                seen.add(kw_lower)
                unique_keywords.append(kw)

        if unique_keywords:
            return unique_keywords[:5]

        # Fallback: Regular nouns (basic extraction)
        words = text.split()
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "what", "how", "why", "which",
                      "이란", "무엇", "어떻게", "뭐야", "뭔가요", "인가요", "이에요"}
        keywords = [w for w in words if len(w) > 2 and w.lower() not in stop_words]

        return keywords[:3]

    def _detect_language(self, text: str) -> str:
        """Detect language of text"""
        korean_count = len(re.findall(r'[\uac00-\ud7af]', text))
        japanese_count = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))

        if korean_count > japanese_count and korean_count > len(text) * 0.1:
            return "ko"
        elif japanese_count > korean_count and japanese_count > len(text) * 0.1:
            return "ja"
        return "en"

    def _is_comprehensive_query(self, text: str) -> bool:
        """
        Detect if query requires comprehensive answer (listing multiple items)

        Patterns that indicate comprehensive queries:
        - Asking for tools, options, methods (plural or list-type)
        - Korean: ~들, 목록, 종류, 알려주세요, 무엇이 있나요
        - Japanese: ~たち, 一覧, 種類, 教えてください
        - English: all, list, what are, types of
        """
        text_lower = text.lower()

        # Korean patterns for comprehensive queries
        korean_patterns = [
            r'알려주세요',      # Tell me (about)
            r'알려줘',          # Tell me (casual)
            r'무엇이\s*있',     # What are there
            r'뭐가\s*있',       # What's there (casual)
            r'어떤\s*것들?이',  # What kinds of
            r'종류',            # Types/kinds
            r'목록',            # List
            r'들이?\s*(있|뭐)', # Plural marker + existence
            r'모든',            # All
            r'전체',            # Entire/whole
            r'옵션',            # Options
            r'방법들',          # Methods (plural)
            r'툴|도구',         # Tools
        ]

        # Japanese patterns
        japanese_patterns = [
            r'教えてください',   # Please tell me
            r'何がありますか',   # What is there
            r'どんな.*があり',   # What kinds are there
            r'種類',            # Types
            r'一覧',            # List
            r'すべて',          # All
            r'全て',            # All (kanji)
            r'オプション',      # Options
            r'ツール',          # Tools
        ]

        # English patterns
        english_patterns = [
            r'\ball\b',         # all
            r'\blist\b',        # list
            r'what are',        # what are
            r'types of',        # types of
            r'kinds of',        # kinds of
            r'options',         # options
            r'tools',           # tools
            r'methods',         # methods
            r'which.*are',      # which ... are
        ]

        all_patterns = korean_patterns + japanese_patterns + english_patterns

        for pattern in all_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _is_deep_analysis_query(self, text: str) -> bool:
        """
        Detect if query requests deep, detailed analysis

        Triggers thorough search with more results and detailed response.

        Patterns:
        - Korean: 자세하게, 상세하게, 소상히, 깊이, 심층
        - Japanese: 詳しく, 詳細に, 深く
        - English: deep think, ultra deep think, in detail, thoroughly
        """
        text_lower = text.lower()

        # Korean patterns for deep analysis
        korean_patterns = [
            r'자세하게',        # In detail
            r'자세히',          # In detail
            r'상세하게',        # In detail (formal)
            r'상세히',          # In detail (formal)
            r'소상히',          # In detail (literary)
            r'소상하게',        # In detail (literary)
            r'깊이',            # Deeply
            r'깊게',            # Deeply
            r'심층',            # In-depth
            r'심도\s*있게',     # In-depth
            r'철저하게',        # Thoroughly
            r'철저히',          # Thoroughly
            r'구체적으로',      # Specifically
            r'면밀하게',        # Meticulously
            r'면밀히',          # Meticulously
        ]

        # Japanese patterns
        japanese_patterns = [
            r'詳しく',          # In detail
            r'詳細に',          # In detail
            r'深く',            # Deeply
            r'徹底的に',        # Thoroughly
            r'具体的に',        # Specifically
            r'綿密に',          # Meticulously
        ]

        # English patterns
        english_patterns = [
            r'deep\s*think',        # deep think
            r'ultra\s*deep',        # ultra deep
            r'in\s*detail',         # in detail
            r'detailed',            # detailed
            r'thorough',            # thorough
            r'thoroughly',          # thoroughly
            r'in[\s-]*depth',       # in-depth
            r'comprehensive',       # comprehensive
            r'exhaustive',          # exhaustive
            r'elaborate',           # elaborate
        ]

        all_patterns = korean_patterns + japanese_patterns + english_patterns

        for pattern in all_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _get_language_instruction(self, language: str) -> str:
        """Get language instruction for prompt"""
        if language == "ko":
            return "Please respond in Korean (한국어로 답변해주세요)."
        elif language == "ja":
            return "Please respond in Japanese (日本語で回答してください)."
        return ""

    def _no_results_message(self, language: str) -> str:
        """Get no results message in appropriate language"""
        if language == "ko":
            return "관련 정보를 찾을 수 없습니다."
        elif language == "ja":
            return "関連情報が見つかりません。"
        return "No relevant information found."

    def _clean_response(self, text: str) -> str:
        """Clean LLM response - remove thinking tokens and normalize whitespace"""
        # Remove complete thinking blocks: <think>...</think>, <thinking>...</thinking>
        text = re.sub(r'<think(?:ing)?>\s*.*?\s*</think(?:ing)?>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove incomplete thinking blocks (opening tag without closing)
        text = re.sub(r'<think(?:ing)?>\s*.*', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Remove content before closing tag (closing tag without opening)
        text = re.sub(r'^.*?</think(?:ing)?>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Clean up multiple newlines and whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def init_system(self) -> Dict[str, bool]:
        """
        Initialize the hybrid RAG system

        Returns:
            Status of each component
        """
        status = {}

        # Check embedding service
        status["embedding_service"] = self.embedding_service.health_check()

        # Initialize vector index
        status["vector_index"] = self.vector_rag.init_vector_index()

        # Check graph connection
        try:
            self.graph.query("RETURN 1")
            status["graph_connection"] = True
        except Exception:
            status["graph_connection"] = False

        return status

    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        # Vector stats
        vector_stats = self.vector_rag.get_vector_stats()

        # Graph stats
        try:
            graph_stats = self.graph.query(
                """
                MATCH (d:Document) WITH count(d) as docs
                MATCH (c:Chunk) WITH docs, count(c) as chunks
                MATCH (e:Entity) WITH docs, chunks, count(e) as entities
                MATCH ()-[r]->() WITH docs, chunks, entities, count(r) as rels
                RETURN docs, chunks, entities, rels
                """
            )
            if graph_stats:
                graph_stats = graph_stats[0]
            else:
                graph_stats = {"docs": 0, "chunks": 0, "entities": 0, "rels": 0}
        except Exception:
            graph_stats = {"docs": 0, "chunks": 0, "entities": 0, "rels": 0}

        return {
            "documents": graph_stats["docs"],
            "chunks": graph_stats["chunks"],
            "entities": graph_stats["entities"],
            "relationships": graph_stats["rels"],
            "embeddings": vector_stats["with_embedding"],
            "embedding_coverage": f"{vector_stats['coverage']:.1f}%"
        }


def get_hybrid_rag() -> HybridRAG:
    """Get a configured HybridRAG instance"""
    return HybridRAG()


if __name__ == "__main__":
    # Test HybridRAG
    print("Testing Hybrid RAG System...")
    print("=" * 50)

    rag = HybridRAG()

    # Initialize system
    print("\n1. Initializing system...")
    status = rag.init_system()
    for component, ok in status.items():
        print(f"   {component}: {'OK' if ok else 'FAILED'}")

    # Get stats
    print("\n2. System statistics:")
    stats = rag.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    # Test queries
    print("\n3. Testing queries...")

    test_queries = [
        ("What is GraphRAG?", "vector"),
        ("What is the relationship between Document and Chunk?", "graph"),
        ("Explain how entity extraction works in detail", "hybrid"),
    ]

    for question, expected_strategy in test_queries:
        print(f"\n   Q: {question}")

        # Classify
        query_type = rag.router.classify_query(question)
        print(f"   Classified as: {query_type.value} (expected: {expected_strategy})")

        # Query (if system is ready)
        if all(status.values()) and stats["chunks"] > 0:
            result = rag.query(question, strategy="auto")
            print(f"   Strategy used: {result['strategy']}")
            print(f"   Sources: {result['sources']}")
            print(f"   Answer: {result['answer'][:100]}...")

    print("\n" + "=" * 50)
    print("Hybrid RAG test completed!")
