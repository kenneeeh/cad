# CAD: analog opamp sizing

KU Leuven Computer-Aided IC Design project: ngspice simulation, a Gymnasium circuit environment, PyTorch TD3, and an MCP-based LLM sizing harness.

This repository is a snapshot of the working project, including local changes, tests and reports. The original GitLab history and remote are not included.

- Environment and dependencies: [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md), `requirements.txt`.
- LLM workflow: [llm/README.md](llm/README.md).
- Validation tests and reports: `codex_tests/`.

Create and activate a Python environment, install the requirements, and install ngspice for your operating system. Activate the environment before launching the LLM harness so its `python` MCP command uses that interpreter. Existing setup reports may contain paths specific to the original machine.

Credentials, virtual environments, tool executables, compiled SAC baseline binaries, generated experiment directories and test artifacts are excluded. The optional SAC baseline requires separately supplied binaries.
