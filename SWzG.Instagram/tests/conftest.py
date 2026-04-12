import sys
from pathlib import Path

# Allow tests to import from src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
