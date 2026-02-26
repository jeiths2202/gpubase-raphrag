"""CLI entry point - delegates to local_coder.main()."""

import sys
import os

# Ensure parent package is importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openframe_code.core import main


def run():
    """Entry point for 'ofcode' command."""
    main()


if __name__ == "__main__":
    run()
