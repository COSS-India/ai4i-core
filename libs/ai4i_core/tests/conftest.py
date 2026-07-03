"""Pytest configuration for ai4i_core library tests."""

import sys
from pathlib import Path

# Allow `import ai4i_core` from the package root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
