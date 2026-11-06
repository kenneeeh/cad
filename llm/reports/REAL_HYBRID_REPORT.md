# One real LLM-controlled hybrid experiment

2026-11-05. One Antigravity campaign, model `gemini-3.8-flash-low`, existing
coordinator/sizing-specialist configuration and seven MCP tools. The required
evaluation/replay/warmup/training/intervention/training sequence completed.
CLI status **SUCCESS**, exit code 0. **No feasible design was found.** No second
experiment, simulator retry campaign, implementation edit, commit or push followed.

Evidence: [validated summary](runs/real_hybrid_20261105_211343/summary.json),
[full candidate archive](runs/real_hybrid_20261105_211343/candidates.jsonl),
[backend calls](runs/real_hybrid_20261105_211343/session_x9gqe3dw/calls.jsonl),
[public native events](runs/real_hybrid_20261105_211343/public_events.jsonl),
[original final response](runs/real_hybrid_20261105_211343/final_result.json).

## Stages and results

Each batch used the unchanged saved TD3 settings: seed 123456, noise .03,
batch 64, actor lr .0005, critic lr .001, delayed actor interval 2. The prompt
specified the requested sequence and step counts, without any sizing changes.

| Stage | Circuit evaluations / resets | Best reward in stage | Best archive reward so far | Replay size after stage |
|---|---:|---:|---:|---:|
| Initial supplied design | 1 / 0 | -1.380930 | -1.380930 | 0; insertion deferred |
| Two LLM-chosen candidates | 2 / 0 | -0.779097 | -0.779097 | 0; three records pending |
| warmup(10) | 10 / 1 | -0.953090 | -0.779097 | 13: three imports + ten random |
| First train(20) | 20 / 2 | -2.215930 | -0.779097 | 33 |
| One LLM intervention | 1 / 0 | -0.891672 | -0.779097 | 33; intervention deferred |
| Second train(20) | 20 / 2 | -1.340473 | -0.779097 | 54; intervention imported |
| **Total** | **54 / 5 = 59 attempts** | | | **54** |

The backend limit was 60; one attempt remained unused. There were no failed
simulator attempts. All 54 archived evaluations passed offline checks of physical
grids, float32 action reconstruction, finite normalized specs, reward and feasibility.
These checks launched no additional simulations.

Warmup made zero gradient updates. Each training batch made **20 critic updates
and 10 delayed actor updates**, for **40 critic / 20 actor updates** overall.
All **four LLM-path records were inserted once**: the supplied initial design,
two actual LLM proposals and one later actual LLM proposal. Insertion cost zero
additional simulations. Five reset evaluations established episode states; resets
were counted separately and were not fabricated replay entries.

## Actual LLM proposals

Both initial refinements were based independently on the supplied initial design.
All changes below came from model tool calls, not from the experiment prompt.

| Candidate | Actual absolute changes | Short hypothesis / measured outcome |
|---|---|---|
| Guided 1 | cap 3.5 -> 0.6 pF; res 6000 -> 3000 ohm | Reduce compensation to improve slew/BW using PM reserve. Slew rose to 30.226 V/us, but PM fell to 36.927 deg; reward -0.779097. |
| Guided 2 | cap 3.5 -> 0.8 pF; res 6000 -> 2500 ohm; wn1 1.75 -> 2.5 um; mn5 17 -> 22 | Combine smaller compensation and device sizing. Gain instead fell to 84.146 V/V; reward -1.190769. |
| Later intervention, based on Guided 1 | cap 0.6 -> 1.2 pF; res 3000 -> 1200 ohm; mp3 18 -> 24; wp3 2 -> 2.75 um; wn1 1.75 -> 2.5 um; mn1 15 -> 20 | Seek phase-margin recovery and higher gain with stronger stages. Gain reached 310.601 V/V, PM 48.774 deg; slew and UGBW still failed; reward -0.891672. |

These are measured associations, not verified transistor operating points or proof
of the proposed gm/pole mechanisms.

## Best measured circuit versus TD3 policy

The overall best was **Guided 1**, ID `design_2e32ab7bf90542eb837b1bcaeeb61ea2`.
Its only changes from initial_design.json are **cap=0.6 pF and res=3000 ohm**.
All 20 actual SI parameters are retained in
[best_design.json](runs/real_hybrid_20261105_211343/best_design.json).

| Measured specification | Best design | Requirement |
|---|---:|---|
| Gain | 188.355 V/V | >=200: **fail** |
| Noise | 3.64974 mV RMS | <=30: pass |
| Phase margin | 36.9268 deg | >=60: **fail** |
| Rising slew rate | 30.2257 V/us | >=30: pass |
| UGBW | 28.5419 MHz | >=100: **fail** |
| Current | 110.653 uA | Optimization scale 200 uA; not a hard constraint |
| Area | 485.451 um^2 | Optimization scale 2000 um^2; not a hard constraint |

Final best reward **-0.7790971768507728**, infeasible. Best random-warmup reward
was **-0.9530904398321964**. Best actor-policy-generated sample across the 40
training steps was **-1.3404729265576762**; the last policy sample scored
**-1.6225404009025848**. Every archived design was infeasible. Policy samples
include exploration noise; no deterministic final actor evaluation was performed.
The good LLM archive entry is not evidence that replay improved the trained actor.

## Persistent state and native specialist evidence

There was exactly one MCP backend session, `session_x9gqe3dw`. The unchanged
TD3Session initialization guard creates its agent/buffer only once. Backend
responses show cumulative policy steps **0 -> 20 -> 40**, memory **13 -> 33 -> 54**,
three initial imported IDs retained/skipped as duplicates, and the intervention
imported at the next reset. Each training call executed the existing real TD3
update path. Later evaluations did not restart learning or clear memory.
This verification uses the single-process lifecycle, inspected code and actual
counters; no extra runtime object-ID or weight-hash instrumentation was added.

Native events show one `circuit-sizing-specialist` invocation and four successfully
delivered messages to the same native ID, `0bd0c884-0323-4593-9f44-28efc2ad764a`,
covering both consultation phases. The coordinator attributes proposals to that
specialist. **Separate specialist reply payloads are not exposed in the captured
public stream**, so the specific advice attribution and receipt of both replies
are not independently verified here. Invocation/message delivery is confirmed;
the report does not upgrade the coordinator's attribution into stronger evidence.

## Time, tokens and problems

- Wall-clock launch time: **140.492 s**; CLI duration: **137.337 s**.
- CLI-reported input: **187,833 tokens**; output: **7,130**; total: **194,963**.
- Separately reported cache-read tokens: **310,806**. Do not add these to the
  displayed total or infer a dollar charge. These are the CLI's exposed usage
  fields, not an independently verified specialist-backend billing total.
- Two schema errors consumed no simulator attempts: `design` instead of
  `parameters` for simulate_design, and `steps` instead of `n_steps` for warmup.
  The model corrected both in the same conversation; no optimization stage was skipped.
- The coordinator's final narrative mislabels a random warmup record as its best
  policy-generated design and describes current as a hard constraint. Both are
  corrected above. Its candidate-2 discussion also confuses mn5 with tail sizing;
  mn5 is the second-stage sink. Physical causal statements remain hypotheses.
- The one-off stream collector expected a `type` field, while the installed CLI
  emits `event`. The public stream was retained; status, response and usage were
  extracted offline from its actual result event without rerunning Antigravity.
  The original cli_summary.json is preserved, including its missing parsed result.

Before larger comparisons, retain independently checkable native specialist replies,
use actual schema field names and origin labels, and separately evaluate final
deterministic actor quality under a planned budget. Controlled repeated seeds and
matched evaluation costs are still needed; this one run establishes working
LLM-controlled replay/warmup/continued-training integration, not learning superiority.

## Files changed

**No project files outside llm/ were modified.** Existing implementation,
hyperparameters, agent definitions, prompt template and historical experiments were
preserved; checked source/configuration hashes match the preflight snapshot.
No dependency, credential, commit, push or refactor was performed.

New files are this report and the single experiment's artifacts under
llm/runs/real_hybrid_20261105_211343/: run-specific prompt/launch script, preflight
hashes, public native events, stderr, final CLI envelope, candidate/simulator data,
validated summary and best design. The launch used the existing CLI/settings/model
with a run-specific prompt and stream output for audit; no project implementation
change was needed. Runtime data remains ignored by Git.
