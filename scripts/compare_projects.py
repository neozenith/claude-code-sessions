#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "rich>=13.0.0",
# ]
# ///
"""
Compare ~/.claude/projects/ with ./projects/ to identify:
1. Newer files in ~/.claude/projects/
2. Files removed from ~/.claude/projects/ (but still in ./projects/)
3. New files in ~/.claude/projects/ (not yet in ./projects/)
"""

import argparse
import logging
from datetime import datetime
from pathlib import Path
from textwrap import dedent

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Configuration
SCRIPT = Path(__file__)
SCRIPT_NAME = SCRIPT.stem
SCRIPT_DIR = SCRIPT.parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent

HOME_PROJECTS = Path.home() / ".claude" / "projects"
LOCAL_PROJECTS = PROJECT_ROOT / "projects"

# Logging
log = logging.getLogger(__name__)
console = Console()


def get_file_map(base_dir: Path) -> dict[str, tuple[Path, float]]:
    """Get map of relative paths to (absolute path, mtime) for all .jsonl files."""
    file_map = {}
    if not base_dir.exists():
        return file_map

    for jsonl_file in base_dir.rglob("*.jsonl"):
        rel_path = str(jsonl_file.relative_to(base_dir))
        mtime = jsonl_file.stat().st_mtime
        file_map[rel_path] = (jsonl_file, mtime)

    return file_map


def format_time(timestamp: float) -> str:
    """Format timestamp as human-readable string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_size(size: int) -> str:
    """Format file size in human-readable format."""
    size_float = float(size)
    for unit in ["B", "KB", "MB", "GB"]:
        if size_float < 1024.0:
            return f"{size_float:.1f}{unit}"
        size_float /= 1024.0
    return f"{size_float:.1f}TB"


def create_file_table(
    files: list[tuple[str, ...]],
    title: str,
    columns: list[str],
) -> Table:
    """Create a rich table for file information."""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    for col in columns:
        table.add_column(col)

    for row in files:
        table.add_row(*row)

    return table


def main(verbose: bool = False) -> None:
    """Compare directories and display results."""
    log.info(f"Comparing {HOME_PROJECTS} with {LOCAL_PROJECTS}")

    # Get file maps
    home_files = get_file_map(HOME_PROJECTS)
    local_files = get_file_map(LOCAL_PROJECTS)

    home_paths = set(home_files.keys())
    local_paths = set(local_files.keys())

    # Header
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]Source:[/bold cyan] {HOME_PROJECTS}\n"
            f"[bold cyan]Local:[/bold cyan]  {LOCAL_PROJECTS}",
            title="[bold]Claude Projects Directory Comparison[/bold]",
            border_style="cyan",
        )
    )
    console.print()

    # 1. NEW FILES: In home but not in local
    new_files = home_paths - local_paths
    if new_files:
        rows = []
        total_size = 0
        for rel_path in sorted(new_files):
            abs_path, mtime = home_files[rel_path]
            size = abs_path.stat().st_size
            total_size += size
            rows.append((
                rel_path,
                format_time(mtime),
                format_size(size),
            ))

        table = create_file_table(
            rows,
            f"🆕 [bold green]NEW FILES[/bold green] in ~/.claude/projects/ ({len(new_files)} files, {format_size(total_size)})",
            ["File", "Modified", "Size"],
        )
        console.print(table)
        console.print()
    else:
        console.print("[green]✅ No new files in ~/.claude/projects/[/green]")
        console.print()

    # 2. REMOVED FILES: In local but not in home (potentially garbage collected)
    removed_files = local_paths - home_paths
    if removed_files:
        rows = []
        total_size = 0
        for rel_path in sorted(removed_files):
            abs_path, mtime = local_files[rel_path]
            size = abs_path.stat().st_size
            total_size += size
            rows.append((
                rel_path,
                format_time(mtime),
                format_size(size),
            ))

        title = (
            f"🗑️  [bold yellow]REMOVED FILES[/bold yellow] from ~/.claude/projects/ "
            f"({len(removed_files)} files, {format_size(total_size)})"
        )
        table = create_file_table(
            rows,
            title,
            ["File", "Last Modified (Local)", "Size"],
        )
        console.print(table)
        console.print(
            "[yellow]These files may have been garbage collected by Claude.[/yellow]"
        )
        console.print()
    else:
        console.print("[green]✅ No files removed from ~/.claude/projects/[/green]")
        console.print()

    # 3. NEWER FILES: Files that exist in both but are newer in home
    common_files = home_paths & local_paths
    newer_files = []
    for rel_path in common_files:
        home_path, home_mtime = home_files[rel_path]
        _, local_mtime = local_files[rel_path]

        # Consider a file newer if it's modified more than 1 second later
        if home_mtime > local_mtime + 1:
            time_diff = home_mtime - local_mtime
            size = home_path.stat().st_size
            newer_files.append((
                rel_path,
                home_path,
                home_mtime,
                local_mtime,
                time_diff,
                size,
            ))

    if newer_files:
        rows = []
        total_size = 0
        for rel_path, home_path, home_mtime, local_mtime, time_diff, size in sorted(
            newer_files
        ):
            total_size += size
            rows.append((
                rel_path,
                format_time(home_mtime),
                format_time(local_mtime),
                f"{time_diff:.0f}s ({time_diff/3600:.1f}h)",
                format_size(size),
            ))

        title = (
            f"🔄 [bold blue]NEWER FILES[/bold blue] in ~/.claude/projects/ "
            f"({len(newer_files)} files, {format_size(total_size)})"
        )
        table = create_file_table(
            rows,
            title,
            ["File", "Home Modified", "Local Modified", "Time Diff", "Size"],
        )
        console.print(table)
        console.print()
    else:
        console.print("[green]✅ All common files are up to date[/green]")
        console.print()

    # Summary
    summary = Table(title="[bold]Summary[/bold]", show_header=False, border_style="cyan")
    summary.add_column("Metric", style="cyan")
    summary.add_column("Count", justify="right", style="bold")

    summary.add_row("Files in ~/.claude/projects/", str(len(home_files)))
    summary.add_row("Files in ./projects/", str(len(local_files)))
    summary.add_row("Common files", str(len(common_files)))
    summary.add_row("New files (need copy)", f"[green]{len(new_files)}[/green]")
    summary.add_row(
        "Removed files (GC'd?)",
        f"[yellow]{len(removed_files)}[/yellow]" if removed_files else "0",
    )
    summary.add_row(
        "Newer files (need sync)",
        f"[blue]{len(newer_files)}[/blue]" if newer_files else "0",
    )

    console.print(summary)
    console.print()

    if new_files or newer_files:
        console.print(
            Panel(
                "[bold]To sync new and updated files, run:[/bold]\n"
                "[cyan]make sync-projects[/cyan]",
                border_style="yellow",
            )
        )
        console.print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=dedent(f"""\
        {SCRIPT_NAME} - Compare Claude projects directories to track changes.

        Compares ~/.claude/projects/ with ./projects/ to identify:
        - New files (not yet copied to local)
        - Removed files (potentially garbage collected by Claude)
        - Newer files (need syncing)

        INPUTS:
        - ~/.claude/projects/**/*.jsonl (source)
        - ./projects/**/*.jsonl (local copy)

        OUTPUTS:
        - Console report with file differences
        """),
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Run script in quiet mode"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Run script in verbose mode"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=(
            logging.DEBUG
            if args.verbose
            else logging.ERROR if args.quiet else logging.INFO
        ),
        format="%(asctime)s|%(name)s|%(levelname)s|%(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    main(verbose=args.verbose)
