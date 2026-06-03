#!/usr/bin/env bash
# ADR3.2 round-2 — Llama-3.1-8B ONLY, re-instrumented after a tmp/ wipe destroyed
# the prior run's result JSONs + logs. Results now land in bench_results/ (OUTSIDE
# tmp/) so a `rm -rf tmp/` cannot destroy evidence. Driver also lives here (durable).
# Llama-3.1-8B (128k, 8B) × {reground,strict,flat} × {day,week,month} = 9 cells,
# reground first. Extraction resumes from the 536 cached summaries (instant cache hits).
set -uo pipefail

RD="bench_results/summary_bench_adr32"        # DURABLE results dir (not tmp/)
SINCE="2025-11-01"
REPORT="docs/plans/summariser-G10-REPORT-adr32.md"
CLI="uv run --frozen -m claude_code_sessions.summarise_cli"
mkdir -p "$RD"
LOG="$RD/sweep_llama.log"

echo "=== ADR3.2 round-2 LLAMA-ONLY (re-instrumented) START $(date -u +%FT%TZ) ===" | tee -a "$LOG"
echo "results -> $RD (durable) | model: Llama-3.1-8B | strategies: reground strict flat | grains: day week month | since: $SINCE" | tee -a "$LOG"

for strat in "reground" "strict" "flat"; do
  for grain in "day" "week" "month"; do
    id="Llama-3.1-8B__${strat}__${grain}"
    echo "--- RUN $id @ $(date -u +%FT%TZ) ---" | tee -a "$LOG"
    $CLI run --id "$id" --since "$SINCE" --results-dir "$RD" >>"$LOG" 2>&1 \
      || echo "CELL ERROR (recorded as data if file written): $id" | tee -a "$LOG"
  done
done

echo "=== REPORT $(date -u +%FT%TZ) ===" | tee -a "$LOG"
$CLI report --results-dir "$RD" --output "$REPORT" >>"$LOG" 2>&1
echo "=== ADR3.2 round-2 LLAMA-ONLY COMPLETE $(date -u +%FT%TZ) ===" | tee -a "$LOG"
