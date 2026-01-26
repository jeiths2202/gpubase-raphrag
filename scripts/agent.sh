#!/bin/bash
# KMS AI Agent CLI Launcher
# Usage: ./agent.sh [options]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Change to project root
cd "$PROJECT_ROOT"

# Run the CLI agent
python -m cli.agent "$@"
