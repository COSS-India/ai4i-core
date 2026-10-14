import sys
from pathlib import Path

# Jobs import `bootstrap.*` and `jobs.*` from the service root, as main.py does.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
