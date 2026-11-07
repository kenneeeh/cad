# CAD sizing workflow

Use only coordinator and circuit-sizing-specialist, with native Antigravity
delegation/messaging. Only the coordinator inherits MCP. The specialist has no
tools, shell or writes. Use the same inherited model; do not add roles.

Use get_problem for current physical grids, units, targets and budget. Use archive
IDs and absolute changes for refinement. Python handles validation, reward,
feasibility, differences and ranking. A positive reward does not prove feasibility.
Use the verified opamp-physics device map and sizing-experiments policy. Explore
major violations with justified changes, including coupled values where needed;
refine near-feasible designs with smaller area/current and margin trade-offs.
Prefer independent probes for uncertain effects and wait
for measurements. Refine a promising measured LLM/TD3 base rather than repeatedly
returning to the initial circuit. Preserve hard margins when optimizing area/current.
Zero UGBW/PHM is a measured penalized fallback, not a simulator failure.

Follow the selected strategy's phase order and switch conditions. Use warmup/train
only in its TD3 phases, with large batches on the same persistent learner and memory.
Consult the specialist in LLM phases, not before a required TD3-first phase. Never edit source,
write scripts, run shell/browser/separate TD3 processes or restart MCP to renew its
budget. Reuse compact summaries and the specialist. Separate hypotheses from
measured evidence; do not invent operating points or claim TA/PVT validation.
No unnecessary repository reads or file/resource discovery; supplied skills and MCP
measurements are the experiment context.
Fixed modes complete the predefined schedule despite feasible or positive rewards.
Adaptive mode completes mandatory warmup, then chooses methods; document why neither
remaining method is useful before stopping voluntarily. Otherwise stop only at
budget/resource/execution limits. Stagnation is a method decision, not an automatic stop.
Read targets from get_problem; use correct units and archive source/phase labels.
Keep short public engineering
justifications, never private chain-of-thought. Report errors and actual usage.

Follow the coordinator's exact tool schemas and local-refinement sequence: full
measured base, one informed consultation, independent probes, measured follow-up.
Reuse returned data; avoid no-op tests, status polling and intermediate essays.
Reuse the same specialist and its actual advice via native reply/wait; do not
reinvoke it for delivery uncertainty. Cached designs retain original measurements
and consume zero simulations. Keep a short tested-changes ledger and choose new
informative experiments to finish the fixed protocol.
