# Project instructions

KU Leuven CAD course project: sizing a two-stage opamp with ngspice, a Gymnasium environment, TD3 and an LLM harness (MCP + Antigravity CLI). The goal of working with the agent here is to **leave the code tidier and more readable without changing its behavior**.

## Documents

- [course/CAD_Instructions_2026.pdf](course/CAD_Instructions_2026.pdf): the assignment. It is the source of truth for what gets delivered.
- [README.md](README.md), [ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md) and [llm/README.md](llm/README.md): structure, environment and harness design.
- Each fact lives in one document. If it is already in another, link to it instead of repeating it.

## Scope

- Only tidiness and readability: names, structure, long functions, duplicated or dead code, imports, formatting. **Behavior does not change.**
- Do not change the TD3 math (`td3/`), reward and normalization (`circuit_env.py`), measurements (`ngspice_interface/`), hyperparameters, prompts, or the skills in `llm/.agents/` unless the user asks.
- Do not touch `course/`, `references.csv`, `output_figs/` or `codex_tests/llm_history/`. Do not delete pre-existing dead code silently: mention it and let the user decide.
- If something looks like a bug, do not fix it silently: name it, explain it and ask for a decision.
- A tidying change and a behavior change never go in the same commit.

## Environment and commands

Python 3.12 with a venv in `.venv`; ngspice installed on the system. Dependencies are in `requirements.txt`.

| Command | What it does |
|---|---|
| `pip install -r requirements.txt` | Installs the dependencies. |
| `python -B -m unittest codex_tests.test_persistent_session codex_tests.test_replay_injection codex_tests.test_mcp_server codex_tests.test_multi_agent codex_tests.test_efficiency` | LLM harness tests; they never call a model. |
| `CAD_PERSISTENT_REAL=1 python -B -m unittest codex_tests.test_persistent_session.TestRealPersistentMCP` | Real test with MCP, ngspice and TD3; it does not call a model either. |
| `python test_circuit_env.py` | Quick environment check. |
| `python ngspice_interface/unit_test.py` | Simulator check. |

`python llm/run_experiment.py` **calls a model and uses the user's quota**: never run it without the user's explicit permission. The same applies to long `td3_runner.py` runs.

## Definition of done

- The tests in the table pass, actually executed. Never claim they passed without running them.
- Observable output is the same as before: same public functions, same command-line arguments, same file formats (`candidates.jsonl`, `summary.json`, `calls.jsonl`).
- The change stays within the agreed scope and is split into small steps that can be reviewed separately.
- Before delivering, review your own diff: ambiguous names, unnecessary parameters, comments that repeat the code, redundant checks, fallbacks and unused abstractions.

## Style

- Short functions with a single responsibility; if a function needs commented sections, split it.
- Names and types should be enough; comments explain why, not what.
- Each function receives only what it needs, not a whole object to pull two fields from.
- No fallbacks that hide errors and no bare `except`.
- File order: module docstring, imports (standard library, third party, local), constants, then functions and classes; the main function first and its helpers in call order. In tests, helpers go after the suites.
- Naming: `snake_case` for functions and variables, `PascalCase` for classes, `UPPER_CASE` for constants. Put units in the name when not obvious (`runtime_s`, `area_m2`).
- 4-space indentation, no tabs (`td3/buffer.py` still uses tabs). Lines up to about 100-120 characters.
- No redundant abstractions or internal checks, and no commented-out code.
- Long files (`llm/run_experiment.py`, `llm/mcp_server.py`, `circuit_env.py`) are first broken into small functions before considering new modules.

## Language

- Code, comments, documentation and commit messages in English.

## Sensitive data

- Secrets and keys go in `.env`, which is not committed. Never copy credentials or paths containing the username into code, tests, reports or commits.
- `llm/runs/`, `codex_tests/artifacts/`, `.venv/` and `no_backup/` are generated output: do not commit them.

## Agent limits

- Do not push without the user's explicit confirmation.
- Commit only when the user approves.
- Do not install or upgrade dependencies without being asked.
- Do not assume folder structure or architecture patterns before they are needed.

## Git

- Work on your own branch created from `main`, not directly on `main`.
- Before starting and before pushing, run `git fetch` and check what is new on `origin/main`.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`, for example `refactor(llm): split run_experiment into helpers`. Common types: `refactor`, `fix`, `feat`, `docs`, `test`, `chore`.
