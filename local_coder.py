#!/usr/bin/env python3
"""Compatibility wrapper - delegates to openframe_code.core.

For direct execution: python local_coder.py [args]
For package usage:    ofcode [args]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from openframe_code.core import main

if __name__ == "__main__":
    main()
