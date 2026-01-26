#!/usr/bin/env python3
"""
RAG Q&A - Interactive Question Answering System
Based on Neo4j Graph + Nemotron LLM
"""
import sys
import re
from langchain_openai import ChatOpenAI
from langchain_neo4j import Neo4jGraph

# Configuration
LLM_URL = "http://localhost:12800/v1"
LLM_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "graphrag2024"


class RAGQA:
    def __init__(self):
        print("Initializing RAG Q&A System...")
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
        self._print_stats()
        print("Ready!\n")

    def _print_stats(self):
        """Print graph statistics"""
        try:
            result = self.graph.query("""
                MATCH (d:Document) WITH count(d) as docs
                MATCH (c:Chunk) WITH docs, count(c) as chunks
                MATCH (e:Entity) WITH docs, chunks, count(e) as entities
                RETURN docs, chunks, entities
            """)
            if result:
                print(f"  Documents: {result[0]['docs']}, Chunks: {result[0]['chunks']}, Entities: {result[0]['entities']}")
        except Exception as e:
            print(f"  Stats unavailable: {e}")

    def _clean_response(self, text: str) -> str:
        """Remove thinking tokens from LLM response"""
        # Remove <think>...</think> blocks (including multiline)
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Remove unclosed <think> blocks (everything from <think> to end)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
        # Remove </think> without opening tag
        text = re.sub(r'</think>', '', text)

        # Split into paragraphs and find the actual answer
        paragraphs = text.strip().split('\n\n')

        # Look for the last paragraph that looks like an actual answer
        # (contains Korean, Japanese, or doesn't start with thinking patterns)
        answer_paragraphs = []
        for para in reversed(paragraphs):
            para = para.strip()
            if not para:
                continue
            # Skip paragraphs that look like thinking
            if re.match(r'^(Okay|First|Looking|I need|Let me|The user|Since|So |Double|Final|Now |Wait|The original|Translating|Also|That)', para):
                continue
            # Keep paragraphs that contain actual answer content
            if re.search(r'[\uac00-\ud7af\u3040-\u30ff\u4e00-\u9fff]', para) or not re.match(r'^[A-Z]', para):
                answer_paragraphs.insert(0, para)
                break

        if answer_paragraphs:
            return '\n\n'.join(answer_paragraphs).strip()

        # Fallback: return last non-empty line
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        return lines[-1] if lines else text.strip()

    def _detect_language(self, text: str) -> str:
        """Detect language of input text"""
        # Count character types
        korean_count = len(re.findall(r'[\uac00-\ud7af]', text))
        japanese_count = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
        chinese_count = len(re.findall(r'[\u4e00-\u9fff]', text))

        # Determine language based on character counts
        if korean_count > japanese_count and korean_count > 0:
            return "Korean"
        elif japanese_count > 0 or (chinese_count > 0 and korean_count == 0):
            return "Japanese"
        else:
            return "English"

    def _clean_translation(self, text: str, target_language: str) -> str:
        """Clean translation output, extracting the actual translated text"""
        # Remove thinking blocks
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)

        # Split into lines and find lines with target language text
        lines = text.strip().split('\n')
        result_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip lines that look like thinking/explanation (English patterns)
            if re.match(r'^(Breaking|Putting|Looking|The |This |I |So |First|Now|Wait|Also|Yes|Another|Let me|"|Okay|No |Final|Looks|Ready|Alternatively|Check for|Make sure|Please note|Double)', line):
                continue
            # Skip lines that contain quotation marks with Japanese (analysis lines)
            if re.search(r'"[^"]*[\u3040-\u30ff][^"]*"', line):
                continue
            # Skip lines with arrows (translation breakdown)
            if ' – ' in line or ' - "' in line:
                continue

            # For Korean, look for Korean characters
            if target_language == "Korean":
                korean_count = len(re.findall(r'[\uac00-\ud7af]', line))
                japanese_count = len(re.findall(r'[\u3040-\u30ff]', line))
                # Accept lines with significant Korean content and no/minimal Japanese
                if korean_count >= 5 and japanese_count == 0:
                    # Remove common prefixes
                    line = re.sub(r'^(번역:|답변:)\s*', '', line)
                    result_lines.append(line)
            # For English, look for lines that aren't Japanese and look like actual content
            elif target_language == "English":
                # Skip if contains Japanese
                if re.search(r'[\u3040-\u30ff]', line):
                    continue
                # Skip think tags
                if '</think>' in line or '<think>' in line:
                    continue
                # Skip very short lines
                if len(line) < 15:
                    continue
                # Remove "Answer:" prefix
                line = re.sub(r'^Answer:\s*', '', line)
                if line:
                    result_lines.append(line)

        # For English, prefer the last substantial line (usually the actual translation)
        if target_language == "English" and result_lines:
            # Filter to get lines that look like actual answers (contain error codes or technical terms)
            answer_lines = [l for l in result_lines if re.search(r'[A-Z_]{3,}|error|occurs|check|refer', l, re.IGNORECASE)]
            if answer_lines:
                return answer_lines[-1]
            return result_lines[-1]

        return '\n'.join(result_lines).strip() if result_lines else ""

    def _translate(self, text: str, target_language: str) -> str:
        """Translate text to target language using LLM"""
        if not text or target_language == "Japanese":
            # No translation needed if target is Japanese (source doc language)
            return text

        # Try translation up to 2 times
        for attempt in range(2):
            if target_language == "Korean":
                prompt = f"""일본어를 한국어로 번역하세요. 번역문만 출력하세요.

{text}

한국어 번역:"""
            else:
                prompt = f"""Translate Japanese to English. Output only the translation.

{text}

English translation:"""

            response = self.llm.invoke(prompt)
            translated = self._clean_translation(response.content, target_language)

            if translated:
                return translated

        # Fallback: return original if translation failed
        return text

    def _safe_str(self, text) -> str:
        """Safely convert text to UTF-8 string, handling encoding errors"""
        if text is None:
            return ""
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='replace')
        return str(text)

    def _extract_keywords(self, question: str) -> list:
        """Extract meaningful keywords from question"""
        # Extract error codes (patterns like XXX_ERR_YYY, XXX-1234, etc.)
        error_codes = re.findall(r'[A-Z_]+ERR[A-Z_]*|[A-Z]+-\d+|\w+_\w+_\w+', question)

        # Split and filter keywords
        words = question.split()
        keywords = []

        # Add error codes first (highest priority)
        keywords.extend(error_codes)

        # Add other meaningful words (length > 2, not common particles)
        stop_words = {'은', '는', '이', '가', '를', '을', '에', '의', '로', '와', '과', '어떤', '무엇', '어떻게'}
        for word in words:
            clean_word = re.sub(r'[?。、.,!？]', '', word)
            if len(clean_word) > 2 and clean_word not in stop_words and clean_word not in keywords:
                keywords.append(clean_word)

        return keywords[:5]

    def _search_chunks(self, question: str, limit: int = 5) -> list:
        """Search relevant chunks from graph"""
        keywords = self._extract_keywords(question)

        # Try keyword search first
        for keyword in keywords:
            if len(keyword) < 2:
                continue
            results = self.graph.query(
                """
                MATCH (c:Chunk)
                WHERE c.content CONTAINS $keyword
                OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
                RETURN c.content AS content, c.index AS idx, collect(DISTINCT e.name)[..5] AS entities
                LIMIT $limit
                """,
                {"keyword": keyword, "limit": limit}
            )
            if results:
                return results

        # Fallback: get recent chunks
        return self.graph.query(
            """
            MATCH (c:Chunk)
            OPTIONAL MATCH (c)-[:MENTIONS]->(e:Entity)
            RETURN c.content AS content, c.index AS idx, collect(DISTINCT e.name)[..5] AS entities
            ORDER BY c.index
            LIMIT $limit
            """,
            {"limit": limit}
        )

    def ask(self, question: str) -> str:
        """Process question and return answer"""
        # Detect user's language
        user_language = self._detect_language(question)

        # Search for relevant context
        chunks = self._search_chunks(question)

        if not chunks:
            no_info_msg = "No relevant information found in the database."
            if user_language == "Korean":
                return "데이터베이스에서 관련 정보를 찾을 수 없습니다."
            elif user_language == "Japanese":
                return "データベースに関連情報が見つかりませんでした。"
            return no_info_msg

        # Build context
        context_parts = []
        for chunk in chunks:
            content = chunk.get('content')
            if content:
                # Safely handle content encoding
                safe_content = self._safe_str(content)[:600]
                context_parts.append(safe_content)
                entities = chunk.get('entities')
                if entities:
                    safe_entities = [self._safe_str(e) for e in entities if e]
                    context_parts.append(f"[Related: {', '.join(safe_entities)}]")

        context = "\n\n".join(context_parts)

        # Generate answer (in Japanese since context is Japanese)
        prompt = f"""以下のコンテキストに基づいて質問に簡潔に答えてください。
コンテキストにない情報は追加しないでください。

コンテキスト:
{context}

質問: {question}

回答:"""

        response = self.llm.invoke(prompt)
        answer = self._clean_response(response.content)

        # Post-process: translate to user's language if needed
        if user_language != "Japanese" and answer:
            answer = self._translate(answer, user_language)

        return answer


def main():
    print("=" * 60)
    print("  RAG Q&A - OpenFrame Error Reference Guide")
    print("=" * 60)
    print()

    try:
        qa = RAGQA()
    except Exception as e:
        print(f"Error: Failed to initialize - {e}")
        sys.exit(1)

    print("Commands:")
    print("  - Type your question and press Enter")
    print("  - Type 'quit' or 'exit' to quit")
    print("  - Type 'stats' to show graph statistics")
    print("-" * 60)

    while True:
        try:
            question = input("\nQ: ").strip()

            if not question:
                continue

            if question.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break

            if question.lower() == 'stats':
                qa._print_stats()
                continue

            print("\nA: ", end="")
            answer = qa.ask(question)
            print(answer)
            print("-" * 60)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
