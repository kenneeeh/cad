# Local validation tests and results

The LLM harness implementation is in [../llm](../llm/README.md).
This folder contains tests, reports, historical snapshots and ignored test output.

- `test_references.py`: TA CSV checks; details in `REFERENCES_REPORT.md`.
- `test_mcp_server.py`: MCP adapter/protocol checks; details in `MCP_REPORT.md`.
- `artifacts/`: ignored simulator outputs and caches; `artifacts/mcp/` holds
  the previous MCP tests and initial live-agent experiment.
- `before/`, `circuit_env_changes.patch`, `REPORT.md`, `test_milestones.py` and
  the older log files are historical validation material. Some describe edits
  later reverted; they are not the current harness implementation or a passing
  current regression suite. Use the two specific current test scripts above.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B codex_tests\test_references.py
.\.venv\Scripts\python.exe -B codex_tests\test_mcp_server.py
```

The reference comparison intentionally exits nonzero while documented mismatches
remain. The full MCP suite uses four ngspice simulations and no model calls.
Keep this directory local; it was excluded from the earlier GitLab push.
