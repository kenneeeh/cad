# Development environment

Configured on Windows on 3 November 2026, using `../session1-2.pptx` (Sessions 1&2, slides 4–8) as the primary reference.

## Interpreter and packages

This checkout uses Python 3.12.15 in `.venv`. Its base Python is installed inside this workspace at `../.tools/python/cpython-3.12.15-windows-x86_64-none`; it no longer depends on the separate Thesis project. Keep that base installation and the portable tools alongside this checkout.

`requirements.txt` lists the eleven course dependencies plus `google-genai`, which the existing `utils/save_response.py` imports. `requirements-lock.txt` records the installed versions of these and their dependencies. Packages are isolated in `.venv`; none were installed in the system Python.

| Dependency | Purpose |
| --- | --- |
| numpy | Numerical arrays and measurements |
| scipy | Interpolation and numerical optimization |
| matplotlib | Circuit and learning plots |
| pyyaml | Circuit configuration files |
| pandas | Tabular data |
| gymnasium | Reinforcement-learning environment API |
| torch | TD3 neural networks and automatic differentiation |
| mcp[cli] | Model Context Protocol SDK and CLI |
| pydantic | Structured input and output validation |
| python-dotenv | Load local environment variables when the harness uses it |
| ipykernel | Python execution in notebooks |
| google-genai | Google response types used by the supplied helper |

An interpreter executes Python. A virtual environment isolates a project's installed packages while using a base interpreter. A package supplies importable Python code. A VS Code extension adds editor features and does not replace installing Python packages. uv creates environments and installs packages; ngspice is a separate simulator executable.

## VS Code

Open `../CADproject.code-workspace`, or open this `cad-git` directory as a folder. Settings also support the existing parent-folder workspace. The four useful Microsoft extensions (Python, Pylance, Python Debugger, Jupyter) were already installed; no new extensions were needed. Their roles are interpreter management, completion/type analysis, debugging, and notebook integration respectively.

The local `.vscode/settings.json` selects `.venv/Scripts/python.exe` by default, starts terminals in this checkout, and exposes portable uv and ngspice to those terminals. The parent folder has equivalent settings pointing into this checkout. Existing cached interpreter selections may need `Python: Select Interpreter` once. Choose this checkout's `.venv/Scripts/python.exe`; select the same environment as the notebook kernel. Live editor selection cannot be verified from configuration files alone.

PowerShell activation is optional. The existing Restricted policy was not changed. From this checkout, run:

```powershell
.\.venv\Scripts\python.exe --version
..\.tools\uv.exe pip check
..\.tools\uv.exe pip install -r requirements.txt
..\.tools\ngspice.cmd -b ..\.tools\divider.cir
```

The new VS Code terminals set uv's cache to `../.tools/uv-cache`. Outside VS Code, set `$env:UV_CACHE_DIR = "$PWD\..\.tools\uv-cache"` if needed. In Command Prompt, `.venv\Scripts\activate.bat` provides activation without PowerShell scripts. Run project modules from this checkout's root because starter paths depend on the current working directory. Debug configurations should likewise use this folder as their working directory.

## Simulator portability change

The existing `NgspiceWrapper.simulate` hardcoded a Linux executable, shell redirection to `/dev/null`, and Unix-style exit-code handling. It now calls `subprocess.run` with an argument list. This handles spaces in paths and checks the actual process return code while preserving the existing result convention: 0 means success and 1 means simulator failure. A missing executable raises an explicit Python error rather than reporting success.

Executable selection is: `NGSPICE_EXECUTABLE` override, the course student-server path if present, `ngspice_con` or `ngspice` on PATH, then the portable Windows installation at `../.tools/ngspice/Spice64/bin/ngspice_con.exe`. No circuit measurements, rewards, sizing functions, or learning algorithms were implemented. Existing coursework TODOs and netlist output placeholders remain.

The existing ngspice 47 Windows console installation was reused. No simulator reinstall or system PATH changes were required. The Python installation did not overwrite an existing user-level Python command shim. No global package installation, credential changes, commits, pushes, or branch switches were performed.

The environment and `.vscode` settings are already ignored by this repository's `.gitignore`. Requirements and this explanation remain available for review as untracked files, and the wrapper portability change remains uncommitted.

## Validation results

All twelve direct dependencies import, as do `ngspice_interface`, `circuit_env`, `td3`, `utils.plotting`, `utils.saving`, `utils.save_response`, `td3_runner`, and `baseline_runner`. PyTorch 2.15.0+cpu passed tensor arithmetic and gradient checks. uv checked all 100 installed packages and found compatible dependencies. The wrapper loaded the supplied YAML and circuit netlist. ngspice returned the expected 0.5 V for a resistor divider, and the wrapper returned 0 for valid input (including a filename with spaces) and 1 for a nonexistent netlist. `git diff --check` passed. No training, LLM provider calls, or incomplete circuit-sizing routines were run.
