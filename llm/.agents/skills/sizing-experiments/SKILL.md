---
name: sizing-experiments
description: Chooses valid, interpretable physical sizing changes from measured evidence.
---

Use get_problem for current numerical grids, units, targets and reward convention.
Bounds are inclusive; parameters are absolute physical values, not RL actions.
Convert um/nm/pF to SI before submission. Python rejects rather than repairs inputs.
Distinguish hard constraints from area/current optimization scales; positive reward
alone does not prove feasibility.

Explore major violations with a measured bottleneck and a physically justified
change. Two coupled parameters are appropriate when their interaction addresses
the bottleneck or protects a vulnerable constraint; do not force separate tests.
Refine near-feasible/feasible bases with smaller grid-aligned changes to area/current
while protecting hard constraints and useful margins. Use one short hypothesis
and trade-off; justify larger jumps or broader changes by the available evidence.
Do not spend the budget making tiny changes that cannot address a major violation.

For uncertain effects, prefer probe_parameters: test a few distinct, small,
one-parameter perturbations of the SAME measured base. Each changes dictionary
is independent, not cumulative. Include the risk to other constraints; compare
the returned measurements before the next hypothesis. Probes are measured finite
changes, not analytical gradients or guaranteed improvements. A clear single
candidate can use evaluate_candidate without a probe batch.

Choose bases using measured feasibility, violations and margins as well as reward.
Use promising TD3 designs too; do not repeatedly restart at the initial circuit.
For feasible designs, refine area/current while preserving hard-constraint margins.
For infeasible designs, address the bottleneck and protect useful existing margins.
Check recent base/change/outcome history to avoid identical or failed repeats;
retesting needs a changed context and stated reason. Preserve the best verified ID.
Combine individually successful modifications when testing their interaction is
informative; inspect the combined measurement rather than assuming additivity.
Keep a compact ledger of base ID, changes and outcome. Reuse identical measured
vectors. A cached response retains its original ID/parent and measurement index,
uses zero attempts, and does not advance the fixed simulation schedule. A no-op
is rejected without simulation; choose a genuinely new informative design next.

Wait for actual measurements before the next dependent modification. Keep only a
compact recent history and one short hypothesis/trade-off. Report returned values
and source/phase correctly: random warmup is not an actor-policy sample, and a
noisy sample is not final deterministic actor quality. SI API units are m, F, ohm,
A, m^2, Hz; displayed um^2 = m^2*1e12 and uA = A*1e6. Never guess a unit conversion
or precise numerical prediction without measured sensitivity evidence.
