# Plan Gap State Machines

- Codify a Script based statemachine to coordinate the /plan-gap skill phases so the LLM is not managing the state and this is deterministic and evidenced based gates and the state machine script is delegating out to subagents. We are creating our own version of the Claude Code Workflows feature with a generalised statemachine that is reusable.
- The script should also be able to exrtact and template the current ticket into single document from the document hierarchy path of context to the ticket. eg linked path from the root document drilling down to an actual ticket could be composed by the script into a single consolidated prompt like following the path of a tree data structure from root to a leaf and appending them all together.
- migrate from `/loop` to `/goal` in the execution plan
- separate the stateful instructions: for that current state only pull in the instruction for that state and that state alone
  - understand paused states and state resumption and discontinued sessions attempting to resume and understanding state effectiveness
  - event driven systems triggering wake ups?
  - state transitions should be evidence based
  - generalise state modelling as a new plan-gap in future to be able to re-leverage the state-machine for a config driven state-machine
- also a script that extracts the claude code session logs to evaluate what parts of the lan actually loaded into memory and which failed to load, as well as the token cost, time costs
- curate specialised subagents
- need to be able to get git worktrees working for parallel evaluations of repeatable plan effectiveness across the different models and a curated way of tracking plan-gaps effectiveness over time
