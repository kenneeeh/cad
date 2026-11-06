---
name: sizing-experiments
description: Chooses valid, interpretable physical sizing changes from measured evidence.
---

Use get_problem for current numerical grids, units, targets and reward convention.
Bounds are inclusive; parameters are absolute physical values, not RL actions.
Convert um/nm/pF to SI before submission. Python rejects rather than repairs inputs.
Distinguish hard constraints from area/current optimization scales; positive reward
alone does not prove feasibility.

For each decision: inspect a measured base and its limiting constraint; choose
one physical hypothesis; change ONE parameter, normally by one or a few grid
steps; state the expected direction and likely trade-off. Two coupled parameters
are allowed with a clear physical reason. Three or more changes, or a large grid
jump, need an explicit reason they cannot reasonably be tested separately. This
is an instruction policy, not an added Python restriction.

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

Wait for actual measurements before the next dependent modification. Keep only a
compact recent history and one short hypothesis/trade-off. Report returned values
and source/phase correctly: random warmup is not an actor-policy sample, and a
noisy sample is not final deterministic actor quality. SI API units are m, F, ohm,
A, m^2, Hz; displayed um^2 = m^2*1e12 and uA = A*1e6. Never guess a unit conversion
or precise numerical prediction without measured sensitivity evidence.
