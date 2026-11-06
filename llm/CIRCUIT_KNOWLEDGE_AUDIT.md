# Circuit knowledge and controlled-experiment audit

2026-11-05. Updated agent knowledge/instructions only. No model calls, simulations,
optimization campaign, dependency changes, commit or push.

## Verified topology and sizing controls

Primary source: [TwoStage.cir](../ngspice_interface/files/input_netlists/TwoStage.cir),
MOS instances at lines 24-31 and compensation at lines 32-33. SPICE MOS pin order
is drain/gate/source/bulk. The included p045_TT.sp defines NMOS and PMOS models;
there are no active amplifier subcircuit definitions or X instances to expand.

| Actual devices | Type / circuit section | Verified role and connections | Width, length, multiplicity parameters |
|---|---|---|---|
| mn1, mn2 | NMOS / input stage | Differential pair; gates net2/net1; common source/body net3; drains net4/net5 | wn1, ln1, mn1 shared by both |
| mp1, mp2 | PMOS / input-stage mirror load | Source/body VDD; shared gate net4; mp1 diode-connected at net4, mp2 drains to net5 | wp1, lp1, mp1 shared by both |
| mn3 | NMOS / bias reference | Drain=gate net7; source/body VSS; reference fed by ibias | wn3, ln3, mn3 |
| mn4 | NMOS / tail mirror output | Drain net3, gate net7, source/body VSS; supplies input tail sink | wn4, ln4, mn4 |
| mp3 | PMOS / second stage | Common-source amplifier: gate net5, drain/output net6, source/body VDD | wp3, lp3, mp3 |
| mn5 | NMOS / second-stage bias sink | Drain net6, gate net7, source/body VSS | wn5, ln5, mn5 |
| cc | Capacitor / compensation | net5 to net8 | cap |
| rc | Resistor / compensation | net8 to net6; series with cc between first-stage output and output | res |

This covers all **20** YAML sizing parameters and all **8** MOS instances.
mn2/mp2 have no independent sizing keys. m-parameters are multiplicities, not
widths; changing one pair's shared parameter changes both devices. The fixed ibias
source and output CL are outside the sizing-action vector.

## Findings and corrections

The previous physics skill's short role list was already correct. The experiment's
agent explanations contradicted it: mp1 was called the input pair, mn3 a second-stage
driver, and ln1/lp3 were described as mirror-load lengths. Earlier explanations
also confused mn5 with the input tail. The expanded mapping above and in the
physics skill explicitly distinguishes these devices, shared controls and nodes.

The coordinator previously had no explicit skills list while the specialist did.
Both now load the same two existing skills. This fixes a configuration gap; it
does not prove that it caused the earlier model errors or guarantees future compliance.

The shared bias reference was underexplained. mn3's gate voltage also controls
mn4 and mn5: more reference width/multiplicity does not establish more stage drive.
Under a simple matched saturated-mirror approximation, widening the reference at
fixed reference current can lower gate voltage and mirrored currents. That remains
a conditional heuristic, not a measured operating-point result.

No stale numerical hard targets were found in the active prompts. The actual
[YAML](../ngspice_interface/files/yaml_files/TwoStage.yaml) was verified:
gain >=200 V/V, noise <=30 mV RMS, phase margin >=60 deg, rising slew >=30 V/us,
UGBW >=100 MHz. Area/current remain optimization scales. Agents obtain current
values through get_problem; these targets were not copied into multiple skills.

The DUT was checked for rising-only slew and zero UGBW/PHM no-crossing fallback.
Unit guidance now distinguishes integrated RMS noise, SI API values, um^2 and uA.
The prompts prohibit inventing DC currents, gm, saturation, pole locations,
precise unmeasured predictions or PVT robustness.

## Strategy changes

- One measured base, one bottleneck and one physical hypothesis per experiment.
- Default: one parameter, one or a few valid grid steps. A coupled pair needs a
  physical reason. Three or more changes or a large jump require an explanation
  of why separate controlled tests are inadequate.
- Prefer independent one-parameter probe_parameters candidates around the SAME
  base for uncertain effects. They are finite measurements, not gradients or
  guaranteed improvements. A clear single change can use evaluate_candidate.
- Inspect results before dependent follow-ups. Avoid identical/failed repeats;
  preserve promising properties and constraint margins.
- Select promising measured LLM or TD3 bases using feasibility, violations and
  margins as well as reward. Refine feasible designs for area/current; address
  limiting constraints for infeasible ones. Reuse an initial circuit only when
  needed or explicitly required by an experiment protocol.
- Specialist output stays short: Bottleneck, Hypothesis, exact Changes, Trade-off.
  Consultations remain selective; no extra per-step model interaction.

The experiment template now makes its injected initial-design suggestion conditional,
so it agrees with measured-base reuse while respecting explicit experiment protocols.
These are instruction policies only: no new Python parameter-count validation,
prescribed sizing recipe, agent, tool or infrastructure was added.

## Uncertain physics

gm*ro gain, Miller UGBW scaling and available-current/capacitance slew are qualified
approximations. Bias ratios, headroom, loading, parasitics and the resistor's zero
depend on operating point. Larger devices or more current are not universally
beneficial. Topology identifies connections and roles; simulation tests whether
a proposed direction improves the measured specifications. No DC/pole analysis
was introduced or inferred from transistor names.

## Validation and files

A focused static audit parsed the real transistor pin/model/W/L/m bindings,
verified both model types, compensation connections, all 20 YAML controls and
current hard targets. It checked two role names, skill references, unchanged role
permissions, the seven decorated MCP functions and their unchanged allowlist.
Both specialist tool access and MCP inheritance remain disabled; shell/write
restrictions and coordinator tool access are unchanged.

Two existing tests passed:

    python -B -m unittest codex_tests.test_multi_agent.TestMultiAgent.test_native_roles_restrict_specialist_tools codex_tests.test_multi_agent.TestMultiAgent.test_prompt_uses_one_hypothesis_without_telemetry_schema -v

Evidence: [validation.json](runs/knowledge_audit_20261105_215933/validation.json)
and [test output](runs/knowledge_audit_20261105_215933/test_output.txt).
Protected-file hashes confirm no change to TD3, replay insertion, environment,
reward/configuration, netlist/models, measurements, MCP code or permissions.
Static/manual cross-reading found the active instructions consistent on controlled
changes, independent probes, target lookup, base selection and uncertainty.

Modified only these six active instruction files:

1. .agents/skills/opamp-physics/SKILL.md
2. .agents/skills/sizing-experiments/SKILL.md
3. .agents/agents/coordinator.md
4. .agents/agents/circuit-sizing-specialist.md
5. GEMINI.md
6. experiment.md

New files: this report and before-snapshots, protected hashes, validation.json and
test_output.txt under runs/knowledge_audit_20261105_215933/. Historical run prompts,
measurements and reports were preserved. No Python implementation was modified.

## Changes outside `llm/`

**None.** Existing outside-folder working-tree changes were preserved untouched.

Limitations: wording/configuration checks do not establish improved agent behavior
or sizing performance. No paid experiment was run to test these edits; compliance
remains advisory rather than a new simulator restriction.
