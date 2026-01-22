#!/usr/bin/env python3
"""
Visualization Data Mapper

Parses frontend TSX files to extract API endpoint usage and generates
a mapping JSON file documenting the Section → Visualization → API relationship.

This helps ensure all APIs are tested and that filter changes affect all relevant
visualizations.

Usage:
    uv run python scripts/visualisation_data_mapper.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


# Define sections with their visualizations manually
# This is more reliable than parsing TSX since visualization names aren't in code
SECTION_DEFINITIONS: list[dict] = [
    {
        "id": 0,
        "name": "Dashboard",
        "path": "/",
        "file": "frontend/src/pages/Dashboard.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Summary Stats Cards",
                "apiEndpoint": "/api/summary",
                "chartType": "cards",
            },
            {
                "id": 1,
                "name": "Monthly Costs Table",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "table",
            },
            {
                "id": 2,
                "name": "Top Projects Cards",
                "apiEndpoint": "/api/usage/top-projects-weekly",
                "chartType": "cards",
            },
            {
                "id": 3,
                "name": "Weekly Costs by Project",
                "apiEndpoint": "/api/usage/top-projects-weekly",
                "chartType": "bar",
            },
        ],
    },
    {
        "id": 1,
        "name": "Daily Usage",
        "path": "/daily",
        "file": "frontend/src/pages/DailyUsage.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Daily Costs Chart",
                "apiEndpoint": "/api/usage/daily",
                "chartType": "bar",
            },
            {
                "id": 1,
                "name": "Token Usage Chart",
                "apiEndpoint": "/api/usage/daily",
                "chartType": "bar",
            },
            {
                "id": 2,
                "name": "Daily Costs by Model",
                "apiEndpoint": "/api/usage/daily",
                "chartType": "stacked_bar",
            },
            {
                "id": 3,
                "name": "Daily Tokens by Model",
                "apiEndpoint": "/api/usage/daily",
                "chartType": "stacked_bar",
            },
        ],
    },
    {
        "id": 2,
        "name": "Weekly Usage",
        "path": "/weekly",
        "file": "frontend/src/pages/WeeklyUsage.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Weekly Costs Chart",
                "apiEndpoint": "/api/usage/weekly",
                "chartType": "bar",
            },
            {
                "id": 1,
                "name": "Token Usage Chart",
                "apiEndpoint": "/api/usage/weekly",
                "chartType": "bar",
            },
            {
                "id": 2,
                "name": "Weekly Costs by Model",
                "apiEndpoint": "/api/usage/weekly",
                "chartType": "stacked_bar",
            },
            {
                "id": 3,
                "name": "Weekly Tokens by Model",
                "apiEndpoint": "/api/usage/weekly",
                "chartType": "stacked_bar",
            },
        ],
    },
    {
        "id": 3,
        "name": "Monthly Usage",
        "path": "/monthly",
        "file": "frontend/src/pages/MonthlyUsage.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Monthly Costs Chart",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "bar",
            },
            {
                "id": 1,
                "name": "Token Usage Chart",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "bar",
            },
            {
                "id": 2,
                "name": "Monthly Costs by Model",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "stacked_bar",
            },
            {
                "id": 3,
                "name": "Monthly Tokens by Model",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "stacked_bar",
            },
            {
                "id": 4,
                "name": "Total Cost by Model Pie",
                "apiEndpoint": "/api/usage/monthly",
                "chartType": "pie",
            },
        ],
    },
    {
        "id": 4,
        "name": "Hourly Usage",
        "path": "/hourly",
        "file": "frontend/src/pages/HourlyUsage.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Cost by Hour Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
            {
                "id": 1,
                "name": "Total Tokens Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
            {
                "id": 2,
                "name": "Input Tokens Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
            {
                "id": 3,
                "name": "Output Tokens Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
            {
                "id": 4,
                "name": "Sessions Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
            {
                "id": 5,
                "name": "Events Heatmap",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "heatmap",
            },
        ],
    },
    {
        "id": 5,
        "name": "Hour of Day",
        "path": "/hour-of-day",
        "file": "frontend/src/pages/HourOfDay.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Cost Polar Chart",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "polar",
            },
            {
                "id": 1,
                "name": "Tokens Polar Chart",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "polar",
            },
        ],
    },
    {
        "id": 6,
        "name": "Projects",
        "path": "/projects",
        "file": "frontend/src/pages/Projects.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Cost by Project Bar",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "horizontal_bar",
            },
            {
                "id": 1,
                "name": "Project Details Table",
                "apiEndpoint": "/api/usage/hourly",
                "chartType": "table",
            },
        ],
    },
    {
        "id": 7,
        "name": "Timeline",
        "path": "/timeline",
        "file": "frontend/src/pages/Timeline.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Event Timeline",
                "apiEndpoint": "/api/timeline/events/{project_id}",
                "chartType": "scatter",
                "requiresProject": True,
            },
        ],
    },
    {
        "id": 8,
        "name": "Schema Timeline",
        "path": "/schema-timeline",
        "file": "frontend/src/pages/SchemaTimeline.tsx",
        "visualizations": [
            {
                "id": 0,
                "name": "Schema Evolution Timeline",
                "apiEndpoint": "/api/schema-timeline",
                "chartType": "scatter",
            },
            {
                "id": 1,
                "name": "Path Details Table",
                "apiEndpoint": "/api/schema-timeline",
                "chartType": "table",
            },
        ],
    },
]

# API endpoint to query file mapping
API_TO_QUERY: dict[str, dict] = {
    "/api/summary": {
        "queryFile": "src/claude_code_sessions/queries/summary.sql",
        "functionName": "get_summary",
        "supportsDays": True,
        "supportsProject": True,  # Will be added
    },
    "/api/usage/daily": {
        "queryFile": "src/claude_code_sessions/queries/by_day.sql",
        "functionName": "get_daily_usage",
        "supportsDays": True,
        "supportsProject": True,  # Will be added
    },
    "/api/usage/weekly": {
        "queryFile": "src/claude_code_sessions/queries/by_week.sql",
        "functionName": "get_weekly_usage",
        "supportsDays": True,
        "supportsProject": True,  # Will be added
    },
    "/api/usage/monthly": {
        "queryFile": "src/claude_code_sessions/queries/by_month.sql",
        "functionName": "get_monthly_usage",
        "supportsDays": True,
        "supportsProject": True,  # Will be added
    },
    "/api/usage/hourly": {
        "queryFile": "src/claude_code_sessions/queries/by_hour.sql",
        "functionName": "get_hourly_usage",
        "supportsDays": True,
        "supportsProject": True,  # Will be added
    },
    "/api/usage/top-projects-weekly": {
        "queryFile": "src/claude_code_sessions/queries/top_projects_weekly.sql",
        "functionName": "get_top_projects_weekly",
        "supportsDays": True,
        "supportsProject": False,  # Not applicable for top-N
    },
    "/api/usage/sessions": {
        "queryFile": "src/claude_code_sessions/queries/sessions.sql",
        "functionName": "get_sessions",
        "supportsDays": True,  # Will be added
        "supportsProject": True,  # Will be added
    },
    "/api/projects": {
        "queryFile": None,  # Aggregation endpoint
        "functionName": "get_projects",
        "supportsDays": True,  # Will be added
        "supportsProject": False,  # N/A - this IS the project list
    },
    "/api/timeline/events/{project_id}": {
        "queryFile": "src/claude_code_sessions/queries/timeline_events.sql",
        "functionName": "get_timeline_events",
        "supportsDays": True,
        "supportsProject": True,  # Via path param
    },
    "/api/schema-timeline": {
        "queryFile": "src/claude_code_sessions/queries/schema_timeline.sql",
        "functionName": "get_schema_timeline",
        "supportsDays": True,
        "supportsProject": True,
    },
}


def verify_files_exist(project_root: Path) -> list[str]:
    """Verify that all referenced files exist."""
    errors = []

    for section in SECTION_DEFINITIONS:
        file_path = project_root / section["file"]
        if not file_path.exists():
            errors.append(f"Section file not found: {section['file']}")

    for endpoint, info in API_TO_QUERY.items():
        if info["queryFile"]:
            query_path = project_root / info["queryFile"]
            if not query_path.exists():
                errors.append(f"Query file not found: {info['queryFile']}")

    return errors


def extract_api_calls_from_tsx(file_path: Path) -> list[str]:
    """Extract API endpoint patterns from a TSX file."""
    content = file_path.read_text()

    # Pattern to match useApi calls
    patterns = [
        r'useApi\S*\(`([^`]+)`',  # useApi<T>(`/endpoint${query}`)
        r'useApi\S*\("([^"]+)"',  # useApi<T>("/endpoint")
        r"useApi\S*\('([^']+)'",  # useApi<T>('/endpoint')
    ]

    endpoints = []
    for pattern in patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            # Clean up the match - remove template string parts
            endpoint = match.split("$")[0].strip("/")
            endpoint = "/" + endpoint if not endpoint.startswith("/") else endpoint
            # Remove trailing incomplete paths
            if endpoint.endswith("/"):
                endpoint = endpoint[:-1]
            endpoints.append(endpoint)

    return list(set(endpoints))


def generate_mapping(project_root: Path) -> dict:
    """Generate the complete visualization data mapping."""
    # Verify all files exist
    errors = verify_files_exist(project_root)
    if errors:
        print("Warnings during mapping generation:")
        for error in errors:
            print(f"  - {error}")

    # Enrich sections with API info
    enriched_sections = []
    total_visualizations = 0

    for section in SECTION_DEFINITIONS:
        enriched_section = section.copy()
        enriched_visualizations = []

        for vis in section["visualizations"]:
            enriched_vis = vis.copy()
            endpoint = vis["apiEndpoint"]

            # Add API metadata if available
            if endpoint in API_TO_QUERY:
                api_info = API_TO_QUERY[endpoint]
                enriched_vis["apiFile"] = f"src/claude_code_sessions/main.py:{api_info['functionName']}"
                enriched_vis["queryFile"] = api_info["queryFile"]
                enriched_vis["supportsDays"] = api_info["supportsDays"]
                enriched_vis["supportsProject"] = api_info["supportsProject"]
            else:
                enriched_vis["apiFile"] = None
                enriched_vis["queryFile"] = None
                enriched_vis["supportsDays"] = False
                enriched_vis["supportsProject"] = False

            enriched_visualizations.append(enriched_vis)
            total_visualizations += 1

        enriched_section["visualizations"] = enriched_visualizations
        enriched_sections.append(enriched_section)

    # Gather unique endpoints
    all_endpoints = set()
    for section in enriched_sections:
        for vis in section["visualizations"]:
            all_endpoints.add(vis["apiEndpoint"])

    return {
        "sections": enriched_sections,
        "apiEndpoints": {
            endpoint: API_TO_QUERY.get(
                endpoint,
                {"queryFile": None, "functionName": None, "supportsDays": False, "supportsProject": False},
            )
            for endpoint in sorted(all_endpoints)
        },
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_sections": len(enriched_sections),
            "total_visualizations": total_visualizations,
            "total_api_endpoints": len(all_endpoints),
        },
    }


def main() -> None:
    """Main entry point."""
    # Determine project root (script is in scripts/)
    project_root = Path(__file__).parent.parent

    print("Generating visualization data mapping...")

    # Generate mapping
    mapping = generate_mapping(project_root)

    # Ensure docs directory exists
    docs_dir = project_root / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Write output
    output_path = docs_dir / "visualisation_data_mapping.json"
    with open(output_path, "w") as f:
        json.dump(mapping, f, indent=2)

    print(f"Generated {output_path}")
    print(f"  - {mapping['metadata']['total_sections']} sections")
    print(f"  - {mapping['metadata']['total_visualizations']} visualizations")
    print(f"  - {mapping['metadata']['total_api_endpoints']} API endpoints")


if __name__ == "__main__":
    main()
