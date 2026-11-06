Run a native multi-agent sizing experiment with at most {{budget}} NEW full
ngspice attempts, including failed simulator attempts. {{start}}

Call get_problem once. Retrieve candidate specs by ID, requesting full parameters
only when needed. Ask the diagnostician for physical interpretation when useful;
ask the designer for one targeted change. Consult the strategist only for
stagnation or a material allocation question. Reuse specialists with small packets.

For each refinement call evaluate_candidate(base_design_id, changes, hypothesis)
with absolute physical values. A short hypothesis is the normal explanation.
Python reconstructs the complete design. Use one short physical hypothesis;
do not invent numerical predictions or unmeasured feasibility.

Preserve failed hypotheses and inspect actual measurements. Track current
and best verified IDs, observed trade-offs and remaining budget. get_candidates
provides distinct reward-ranked results. Stop within the budget and retain a better
earlier design when refinement fails. Finish with the best ID, measured reward,
feasibility and a brief engineering explanation. Fixture records are tests.
