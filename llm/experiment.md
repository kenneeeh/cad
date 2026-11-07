Run a two-agent {{mode}} sizing experiment with at most {{budget}} actual ngspice
attempts, including TD3 resets and failures.

Read get_problem once; the selected workflow below takes precedence over generic
phase suggestions. Retrieve candidates only when selecting a measured refinement
base whose full data is not already supplied or retained. Starting suggestion for an LLM phase only, when no useful current-setup
measured base exists or the explicit protocol requires it: {{start}}

Prefer a promising measured base from either LLM or TD3; consider feasibility,
violations and margins, not reward alone. Consult circuit-sizing-specialist
once for local refinement, supplying the full measured base, targets, relevant
grids, margins and recent outcomes. Retain that specialist and wait for its native
reply, without task polling or reinvoking the same question. Retrieve missing sizes with
get_candidates(design_id="ID", include_parameters=True); no format argument.

{{workflow}}

Follow the verified topology: check device roles before hypotheses. Explore major
violations with justified changes, including coupled values where appropriate;
refine near-feasible designs with smaller area/current and margin trade-offs.
Use one short hypothesis/trade-off and explain larger changes. Use independent probe_parameters
changes to the SAME base for uncertainty; evaluate_candidate is enough for a clear
single modification. Inspect results before dependent follow-ups and avoid repeats.
Use probe_parameters(base_design_id="ID", changes_list=[{"parameter": absolute_value}])
for 1..5 independent same-base probes, never parameter_variations. Use
evaluate_candidate(base_design_id="ID", changes={"parameter": absolute_value})
for a targeted refinement. Changes must be nonempty, grid-valid and different
from the base; omit duplicate tests. Inspect results before choosing dependent values.
Keep a compact base/change/outcome ledger. Combine independently successful
changes when their interaction merits a test. Cached results are old measurements
with their original IDs, not new simulations; no-op requests are rejected. Neither
advances the fixed attempt schedule. Choose another informative design instead.
Fixed modes complete the predefined schedule. Adaptive mode completes mandatory
warmup, then independently chooses methods within its ceilings; voluntary stopping
requires a documented assessment that neither remaining method is useful.
Feasibility/positive reward never justify stopping. Budget/resource/error limits
also permit stopping. The fixed LLM-first plateau rule switches phases; adaptive
stagnation only suggests reconsidering the method. Avoid
intermediate essays, repeated consultations and status/resource polling; reuse
returned data. For TD3 calls use warmup(n_steps=N) and train(n_steps=N).

Preserve hard margins when improving feasible designs' area/current; otherwise
prioritize the limiting constraint. Keep current/best IDs, actual units and origin,
failed hypotheses and remaining budget including resets. No invented measurements
or precise predictions; no repository reads, scripts or MCP restarts. Finish with the best
measured ID, reward, feasibility and a brief evidence-based explanation.
Tie each short keep/reject/follow-up decision to its measured candidate ID in the
next hypothesis or final response. Preserve actual advice; never manufacture it.
