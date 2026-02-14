"""
Path setup for token_intel_service.
Ensures the parent directory is in sys.path for importing common_ai.
"""

import sys
import os

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
