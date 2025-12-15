import os
from pathlib import Path

# Server configuration
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8100"))
BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")

# Data paths
PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
PROJECTS_PATH: Path = Path(os.getenv("PROJECTS_PATH", str(PROJECT_ROOT / "projects")))
QUERIES_PATH: Path = Path(__file__).parent / "queries"
PRICING_CSV_PATH: Path = Path(__file__).parent / "data" / "pricing.csv"

# Alternative data source (original location)
HOME_PROJECTS_PATH: Path = Path.home() / ".claude" / "projects"
