# CAD sizing workflow

Use only coordinator and circuit-sizing-specialist, with native Antigravity
delegation/messaging. Only the coordinator inherits MCP. The specialist has no
tools, shell or writes. Use the same inherited model; do not add roles.

Use get_problem for current physical grids, units, targets and budget. Use archive
IDs and absolute changes for refinement. Python handles validation, reward,
feasibility, differences and ranking. A positive reward does not prove feasibility.
Use the verified opamp-physics device map and sizing-experiments policy: one small
change by default, two coupled values with reason, larger changes only with an
explicit justification. Prefer independent probes for uncertain effects and wait
for measurements. Refine a promising measured LLM/TD3 base rather than repeatedly
returning to the initial circuit. Preserve hard margins when optimizing area/current.
Zero UGBW/PHM is a measured penalized fallback, not a simulator failure.

Use warmup/train MCP tools for the same persistent TD3 learner and memory. Add
physics-guided designs first, random diversity next, then alternate bounded
training with occasional interventions. No fixed mixing ratio. Never edit source,
write scripts, run shell/browser/separate TD3 processes or restart MCP to renew its
budget. Reuse compact summaries and the specialist. Separate hypotheses from
measured evidence; do not invent operating points or claim TA/PVT validation.
Read targets from get_problem; use correct units and archive source/phase labels.
Keep short public engineering
justifications, never private chain-of-thought. Report errors and actual usage.

Follow the coordinator's exact tool schemas and local-refinement sequence: full
measured base, one informed consultation, independent probes, measured follow-up.
Reuse returned data; avoid no-op tests, status polling and intermediate essays.
