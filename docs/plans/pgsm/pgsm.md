# Plan Gap State Machines

- Codify a Script based statemachine to coordinate the /plan-gap skill so the LLM is not managing the state and this is deterministic and evidenced based gates
- The script should also be able to exrtact and template the current ticket into single document from the document hierarchy path of context to the ticket.
- migrate from `/loop` to `/goal`
- separate the stateful instructions: for that current state only pull in the instruction for that state and that state alone
  - understand paused states and state resumption and discontinued sessions attempting to resume and understanding state effectiveness
  - event driven systems triggering wake ups?
  - state transitions should be evidence based
  - generalise state modelling as a new plan-gap in future to be able to re-leverage the state-machine for a config driven state-machine
- also a script that extracts the claude code session logs to evaluate what parts of the lan actually loaded into memory and which failed to load, as well as the token cost, time costs
- curate specialised subagents
- need to be able to get git worktrees working for parallel evaluations of repeatable plan effectiveness across the different models and a curated way of tracking plan-gaps effectiveness over time
- Should also look at the underlying state machine backend store interfaces like:
  - Local file system flat files like JSONL akin to how beads worked?
  - sqlite db?
  - Github Issues
  - Notion Kanbans
  - Jira (maybe via Rovo MCP)