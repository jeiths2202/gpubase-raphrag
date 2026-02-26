# OpenFrame Code

OpenFrame 7 Expert CLI - Claude Code-style coding assistant for OpenFrame codebase analysis.

Connects to a local LLM (Qwen3 32B on vLLM) via OpenAI-compatible API.

## Install

```bash
pip install openframe-code
```

## Prerequisites

- **vLLM server** with Qwen3 32B (or compatible model) running with tool calling enabled:
  ```bash
  vllm serve /path/to/model --enable-auto-tool-choice --tool-call-parser hermes
  ```
- **OpenFrame 7 source code** (for `--openframe` mode)

## Quick Start

```bash
# 1. Build index from your of7 source (one-time)
ofcode-build-index --of7-root /path/to/of7

# 2. Run in OpenFrame expert mode
ofcode --openframe

# 3. Or run in general coding assistant mode
ofcode
```

## CLI Options

```
ofcode [OPTIONS]

Options:
  --server URL          vLLM server URL (default: http://192.168.8.11:12810/v1)
  --model NAME          Model name (auto-detected if not specified)
  --openframe           Enable OpenFrame expert mode
  --of7-root PATH       Override of7 source path (default: from index)
  --no-confirm          Skip confirmation for destructive operations
  --show-thinking       Show Qwen3 <think> blocks
  --temperature FLOAT   Sampling temperature (default: 0.7)
  --max-tokens INT      Max response tokens (default: 4096)
  --context-length INT  Context window override (auto-detected)
```

## OpenFrame Tools

In `--openframe` mode, the LLM has access to specialized tools:

| Tool | Description |
|------|-------------|
| `search_of7` | Search C/H files in the of7 codebase |
| `get_module_info` | Module structure and descriptions |
| `get_function_def` | Find function definition with source context |
| `get_header_api` | Header file API summary |
| `get_architecture` | 6-layer architecture diagram |
| `find_callers` | Find all callers of a function |

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/exit` | Exit |
| `/clear` | Clear conversation |
| `/tokens` | Show token usage |
| `/model` | Show model info |
| `/compact` | Compact history |
