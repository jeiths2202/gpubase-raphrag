# PDF Adaptive Embedding AI Service – Implementation Prompt

## Role Definition

You are a **Senior AI Platform Engineer & Architect** specializing in:

* Document AI
* PDF structure analysis
* Multimodal embeddings
* Large-scale RAG systems
* Production-grade AI services

Your task is to **design and implement a production-ready AI service** that embeds PDF documents **without relying on fixed chunk sizes**, while preserving document structure, page references, and semantic integrity.

---

## Problem Statement

PDF documents vary widely in:

* Logical structure (chapters, sections, paragraphs)
* Layout (single/multi-column, headers/footers)
* Content types (text, tables, images, scanned OCR)

A fixed chunk-size embedding approach causes:

* Context fragmentation
* Retrieval inaccuracies
* Loss of semantic and structural meaning

The goal is to build an **adaptive, structure-aware, multimodal PDF embedding service**.

---

## High-Level Objectives

* Understand PDF logical + visual structure
* Generate adaptive chunking strategies per document
* Preserve page numbers and section hierarchy
* Embed text, tables, images, and OCR content
* Evaluate embedding coverage and retrieval quality
* Support scalable, parallel, and fault-tolerant processing

---

## Required System Architecture

### 1. PDF Structure Analysis Module

Implement a pipeline that:

* Classifies document type (manual, report, paper, contract, etc.)
* Extracts logical hierarchy:

  * Title
  * Chapter
  * Section / Subsection
* Analyzes layout:

  * Columns
  * Headers / Footers
  * Footnotes
* Detects content blocks:

  * Paragraph
  * List
  * Table
  * Figure + Caption

**Output:** Structured intermediate representation (IR)

---

### 2. Adaptive Chunk Planning Engine

DO NOT use fixed chunk sizes.

Instead:

* Dynamically determine chunk boundaries based on:

  * Semantic completeness
  * Section boundaries
  * Content type
* Define chunk types:

  * TEXT_CHUNK
  * TABLE_CHUNK
  * IMAGE_CHUNK
  * OCR_CHUNK
* Maintain relationships:

  * parent_section_id
  * previous_chunk_id / next_chunk_id
  * referenced_table_id / figure_id

**Output:** Chunk Plan with metadata

---

### 3. Parallel Embedding Execution

* Execute embeddings **per chunk**, not per page
* Maintain ordering inside the same section
* Preserve page references:

  * page_start
  * page_end
* Support parallel execution with:

  * Retry logic
  * Timeout handling
  * Partial failure recovery

---

### 4. Multimodal Embedding Coverage Validation

Validate that the following are correctly embedded:

* Text

  * No missing paragraphs
  * Correct sentence reconstruction
* Tables

  * Header-value relationship preserved
  * Merged cells handled
* Images

  * Caption linkage
  * Reference from surrounding text
* OCR

  * Confidence scoring
  * Bounding box to page mapping

Produce an **Embedding Coverage Report**.

---

### 5. Embedding Quality Evaluation (Retrieval-Based)

Do NOT rely solely on cosine similarity.

Implement:

* Query-based evaluation

  * Section-level queries
  * Table/figure reference queries
* Hallucination detection

  * Page mismatch
  * Section leakage
* Metrics:

  * Top-k Recall
  * Section Precision
  * Context Coherence Score

---

## Metadata Schema (Mandatory)

Each chunk must include:

```json
{
  "pdf_id": "",
  "chunk_id": "",
  "chunk_type": "",
  "content": "",
  "page_start": 0,
  "page_end": 0,
  "section_path": "2.3.1",
  "parent_section_id": "",
  "relations": {
    "previous": "",
    "next": "",
    "references": []
  },
  "embedding_model_version": "",
  "chunk_version": ""
}
```

---

## Additional Mandatory Considerations

### Versioning

* Support re-embedding with:

  * chunk_version
  * embedding_model_version

### Incremental Re-Embedding

* Detect PDF changes using page-level hash
* Re-embed only affected chunks

### Security

* PDF-level ACL
* Chunk-level access isolation
* Prevent cross-document retrieval contamination

### Operations

* Embedding failure retry strategy
* OCR fallback handling
* Large PDF timeout control
* CPU/GPU workload separation

---

## Deliverables

Provide:

1. System architecture diagram (textual or diagram format)
2. Core module implementations
3. Chunk Planner logic
4. Metadata schema implementation
5. Embedding pipeline
6. Evaluation pipeline
7. Clear documentation and comments

---

## Guiding Principle

> This system is not a “PDF to vectors” tool.
> It is a **structure-preserving knowledge ingestion engine**.

Design every component accordingly.

---

## Output Expectations

* Clean, modular, production-ready code
* Clear separation of concerns
* Explicit error handling
* Extensible design for future multimodal expansion

