# CAD sizing workflow

The coordinator runs a native team with circuit-diagnostician, experiment-designer
and optional optimization-strategist. Only the coordinator has simulation access.
Specialists must use MCP/write-disabled invocations, no shell or filesystem edits.
Use the same inherited model; do not create additional agents or impersonate failures.

Use get_problem for current physical grids, units, targets and budget. Use archive
IDs and absolute changes for refinement. Python handles validation, reward,
feasibility, differences and ranking. A positive reward does not prove feasibility.
Zero UGBW/PHM is a measured penalized fallback, not a simulator failure.

Do not edit source/configuration, run shell/browser/TD3, add analysis tools or
restart the simulator to renew its budget. Reuse compact candidate summaries and
idle specialists. Separate physical hypotheses from measured evidence; do not
invent operating points or claim TA/PVT validation. Keep short public engineering
justifications, never private chain-of-thought. Report errors and actual usage.
