# Archived LLM validation evidence

These files were moved intact out of llm during its consolidation. They retain
original metrics, decisions, failed predictions and CLI/service errors. Paths and
commands inside the old reports describe the implementation at that time and may
no longer exist. Current usage is in ../../llm/README.md.

- VALIDATION_REPORT.md: historical single-agent/token diagnostics.
- MULTI_AGENT_REPORT.md, recorded_run.json: the original five-call multi-agent run.
- communication_check.md/json: historical zero-budget native-agent audit.
- TOOLS_REPORT.md, TOOLS.md: implementation report and guide before consolidation.
- MULTI_AGENT_GUIDE.md: previous native-agent guide.
- runs/: original runtime logs/output, including unsuccessful setup checks.
- REPLAY_REPORT.md and replay_tests_before_cleanup.txt: the earlier, larger replay
  integration and its tests; current code keeps only a small manual insertion API.

This archive is local test/evaluation evidence, not an active framework or TD3
candidate import. Do not push codex_tests. V1's executable workflow has been removed.
