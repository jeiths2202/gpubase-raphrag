#!/usr/bin/env python3
"""REST API for AI Driven RAG System."""
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

from agent import AIAgent
from config import config


# Global agent instance
_agent: AIAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    global _agent
    _agent = AIAgent()
    yield
    if _agent:
        await _agent.close()


app = FastAPI(
    title="AI Driven RAG API",
    description="Pure AI-driven RAG system using local LLM with tool calling",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Query request model."""
    query: str = Field(..., description="User query", min_length=1)
    conversation_history: list[dict] | None = Field(
        default=None,
        description="Previous conversation messages",
    )
    stream: bool = Field(default=False, description="Enable streaming response")


class QueryResponse(BaseModel):
    """Query response model."""
    answer: str
    tool_calls_made: list[dict] = []
    sources: list[str] = []


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Execute a RAG query.

    The AI agent will:
    1. Analyze your query
    2. Decide which tools to use (vector_search, graph_query, document_read)
    3. Execute tools and synthesize a response

    All decisions are made by the LLM - no hardcoded rules.
    """
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    if request.stream:
        async def generate():
            async for chunk in _agent.run_stream(
                request.query,
                request.conversation_history,
            ):
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="text/plain",
        )

    response = await _agent.run(
        request.query,
        request.conversation_history,
    )

    return QueryResponse(
        answer=response.answer,
        tool_calls_made=response.tool_calls_made,
        sources=response.sources,
    )


@app.get("/tools")
async def list_tools():
    """List available tools."""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in _agent.tools.get_all()
        ]
    }


def main():
    """Run the API server."""
    uvicorn.run(
        "api.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
