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

# Domain filtering
# Domains are the first directory under $HOME in encoded project IDs
# e.g., /Users/joshpeak/work/project -> -Users-joshpeak-work-project, domain = "work"
BLOCKED_DOMAINS: list[str] = [
    d.strip() for d in os.getenv("BLOCKED_DOMAINS", "").split(",") if d.strip()
]

# Home prefix for building SQL LIKE patterns against encoded project IDs
# e.g., /Users/joshpeak -> -Users-joshpeak
HOME_PREFIX: str = str(Path.home()).replace("/", "-")


def extract_domain(project_id: str) -> str | None:
    """Extract the domain (first directory under $HOME) from an encoded project ID.

    Project IDs encode filesystem paths with - replacing /:
        -Users-joshpeak-work-project  -> "work"
        -Users-joshpeak-play-myapp    -> "play"
        -Users-joshpeak-.config-foo   -> ".config"

    Returns None if project_id doesn't start with HOME_PREFIX or has no domain segment.
    """
    if not project_id.startswith(HOME_PREFIX):
        return None
    remainder = project_id[len(HOME_PREFIX) :]
    if not remainder.startswith("-"):
        return None
    # remainder is like "-work-project-name", split on "-" starting after the leading dash
    parts = remainder[1:].split("-", 1)
    if not parts or not parts[0]:
        return None
    return parts[0]


def is_project_blocked(project_id: str) -> bool:
    """Check if a project belongs to a blocked domain.

    Returns True if the project's domain is in BLOCKED_DOMAINS.
    Returns False if BLOCKED_DOMAINS is empty or the project has no domain.
    """
    if not BLOCKED_DOMAINS:
        return False
    domain = extract_domain(project_id)
    if domain is None:
        return False
    return domain in BLOCKED_DOMAINS
