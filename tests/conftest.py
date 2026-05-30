"""Shared test fixtures and path configuration."""
import sys
from pathlib import Path

# Add project root to sys.path so 'src' is importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
