# Aborted seed-1 attempt: invalid backend routing

The first seed-1 attempt (`hybrid_wgku3xao`) was stopped after the live audit showed
that Antigravity's effective MCP registration pointed to the older `cad-git`
backend rather than the validated `github-share/cad` checkout. The preflight had
checked the local registration file but failed to query the effective CLI
registration. This was a launch-environment error, not a validated repeatability
result. The original launch manifest and raw logs remain unchanged under
`llm/runs/hybrid_wgku3xao/`.

The partial logs contain **33 actual simulator attempts**, comprising **30 TD3
warmup candidates and 3 resets**; all process return codes are zero. There were
**zero LLM evaluations, zero training steps and zero critic updates**. One random
warmup candidate was feasible, with FoM **0.11333446684596657**; it is not treated as
the outcome of the requested validated hybrid experiment. Token usage was not
recovered after terminating the launcher/process tree.

No validated source, agent, skill, reward, grid, model, circuit or reference-result
file changed. The effective CLI registration was corrected to the validated
checkout. A model-free MCP check with a hard **zero-simulation budget** verified
seed 1, the correct ceiling-based `llm_led` protocol, and rejection of evaluation
only for the zero budget rather than a mandatory-warmup phase. It produced no
simulator attempts. The preflight now checks the effective CLI registration as
well as the local file.

The user explicitly authorized **one fresh replacement run** after this abort.
That run must use a new archive and replay state, with its own 300-attempt cap;
these 33 spent attempts remain separate overhead and are not hidden or imported
into the replacement's candidate history.

Machine-readable accounting: [abort_summary.json](seed1_aborted/abort_summary.json).
