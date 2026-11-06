Run a two-agent {{mode}} sizing experiment with at most {{budget}} actual ngspice
attempts, including TD3 resets and failures.

Read get_problem once; the selected workflow below takes precedence over generic
phase suggestions. Retrieve candidates only when selecting a measured refinement
base. Starting suggestion for an LLM phase only, when no useful current-setup
measured base exists or the explicit protocol requires it: {{start}}

Prefer a promising measured base from either LLM or TD3; consider feasibility,
violations and margins, not reward alone. Consult circuit-sizing-specialist
once for local refinement, supplying the full measured base, targets, relevant
grids, margins and recent outcomes. Retrieve sizes with
get_candidates(design_id="ID", include_parameters=True); no format argument.

{{workflow}}

Follow the verified topology and controlled-change skills: one small grid-aligned
parameter change and one short hypothesis/trade-off by default. Explain coupling
or an unavoidable larger test. Use independent one-parameter probe_parameters
changes to the SAME base for uncertainty; evaluate_candidate is enough for a clear
single modification. Inspect results before dependent follow-ups and avoid repeats.
Use probe_parameters(base_design_id="ID", changes_list=[{"parameter": absolute_value}])
for 1..5 independent same-base probes, never parameter_variations. Use
evaluate_candidate(base_design_id="ID", changes={"parameter": absolute_value})
for a targeted refinement. Changes must be nonempty, grid-valid and different
from the base; omit duplicate tests. Inspect results before choosing dependent values.
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
