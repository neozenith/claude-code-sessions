"""
Claude API Pricing Configuration

Pricing data is stored in data/pricing.csv and loaded directly by DuckDB.
Prices are per million tokens (USD).

Source: https://www.anthropic.com/pricing
"""

from pathlib import Path

# Path to the pricing CSV file
PRICING_CSV_PATH = Path(__file__).parent / "data" / "pricing.csv"


def get_pricing_cte() -> str:
    """
    Generate the pricing CTE for DuckDB SQL queries.

    Returns:
        SQL snippet defining the pricing table as a CTE using read_csv_auto().
    """
    return f"""WITH pricing AS (
    SELECT * FROM read_csv_auto('{PRICING_CSV_PATH}')
)"""
