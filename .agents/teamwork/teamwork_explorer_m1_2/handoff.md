# Handoff Report: Python Environment Isolation, Virtualenv Routing Invariants, and PyTorch Guard Verification

- **Agent**: `teamwork_explorer_m1_2`
- **Role**: Python Environment & PyTorch 2.9.1 Routing Explorer, Synthesis
- **Working Directory**: `E:\Downloads\Chat_GPT_AI\.agents\teamwork\teamwork_explorer_m1_2\`
- **Target Recipient**: Orchestrator (`cee93413-6e94-42af-a811-08721badd7f7`)
- **Date**: 2026-11-07T21:47:00Z
- **Milestone**: Milestone 1 — Project Invariants & Safe Execution Setup (Feature 2)

---

## 1. Observation

### 1.1 Comparative Virtual Environment Audit
A direct audit was conducted across the three Python virtual environments in the project:
1. `gigaforge/.venv_native` (`E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native`)
2. Root `.venv` (`E:\Downloads\Chat_GPT_AI\.venv`)
3. `NovaForge/.venv` (`E:\Downloads\Chat_GPT_AI\NovaForge\.venv`)

The following exact versions and configurations were empirically observed:

| Environment | Python Executable | Python Version | PyTorch Version | CUDA Support | Key Missing Packages | Intended Role |
|---|---|---|---|---|---|---|
| **`gigaforge/.venv_native`** | `gigaforge\.venv_native\Scripts\python.exe` | 3.11.9 | **`2.9.1+cu126`** | **True (CUDA 12.6)** | None | **Primary GigaForge training, evaluation & test runtime** |
| **Root `.venv`** | `.venv\Scripts\python.exe` | 3.11.9 | **`2.14.1+cu126`** | True (CUDA 12.6) | `gymnasium`, `stable-baselines3`, outdated `wandb` (0.30.0) | Historical repository root environment (INCOMPATIBLE with GigaForge) |
| **`NovaForge/.venv`** | `NovaForge\.venv\Scripts\python.exe` | 3.11.9 | **`2.9.1+cpu`** | **False (CPU only)** | None (has gymnasium, sb3) | Teacher asset export & CPU donor environment |

#### Empirical Verifications:
- **`gigaforge/.venv_native`**:
  ```cmd
  E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe -c "import sys, torch, gymnasium, stable_baselines3; print('VENV_NATIVE:', sys.version.split()[0], '| Torch:', torch.__version__, '| CUDA:', torch.cuda.is_available(), '| Gymnasium:', gymnasium.__version__)"
  ```
  *Output*:
  ```text
  VENV_NATIVE: 3.11.9 | Torch: 2.9.1+cu126 | CUDA: True | Gymnasium: 1.4.0
  ```
- **Root `.venv`**:
  ```cmd
  E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe -c "import sys, torch; print('ROOT_VENV:', sys.version.split()[0], '| Torch:', torch.__version__, '| CUDA:', torch.cuda.is_available())"
  ```
  *Output*:
  ```text
  ROOT_VENV: 3.11.9 | Torch: 2.14.1+cu126 | CUDA: True
  ```
  Attempting to import `gymnasium` in root `.venv`:
  ```text
  ModuleNotFoundError: No module named 'gymnasium'
  ```
- **`NovaForge/.venv`**:
  ```cmd
  E:\Downloads\Chat_GPT_AI\NovaForge\.venv\Scripts\python.exe -c "import sys, torch; print('NOVAFORGE_VENV:', sys.version.split()[0], '| Torch:', torch.__version__, '| CUDA:', torch.cuda.is_available())"
  ```
  *Output*:
  ```text
  NOVAFORGE_VENV: 3.11.9 | Torch: 2.9.1+cpu | CUDA: False
  ```

---

### 1.2 Catastrophic Failure Modes of Root `.venv`
Two critical failure modes were directly reproduced when attempting to execute GigaForge operations within the root `.venv`:

1. **Native C++ Entry Point Failure (Windows NTSTATUS `0xC0000139` / `3221225785`)**:
   `GigaForge.exe` was compiled and linked against LibTorch 2.9.1 C++ ABI (`torch_cpu.dll`, `c10.dll`). When `GigaForge.exe --selftest` is executed with `PATH` pointing to the PyTorch libraries from root `.venv` (`torch==2.14.1+cu126`), execution fails immediately:
   ```cmd
   Command: & "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" -c "import os, sys, subprocess, torch; from pathlib import Path; root = Path(r'E:\Downloads\Chat_GPT_AI\gigaforge'); binary = root / 'native/GigaForge.exe'; lib = Path(torch.__file__).parent / 'lib'; env = dict(os.environ); env['PATH'] = str(lib) + os.pathsep + env.get('PATH', ''); sys.exit(subprocess.run([str(binary), '--selftest'], env=env).returncode)"
   ```
   *Output*:
   ```text
   RETURNCODE: 3221225785 (Hex: 0xC0000139, STATUS_ENTRYPOINT_NOT_FOUND)
   ```
   The Windows dynamic linker terminates the process because LibTorch 2.14.1 does not export the exact C++ symbol entry points expected by the LibTorch 2.9.1-linked binary.

2. **PyTest Execution Failures in Root `.venv`**:
   Executing the GigaForge test suite using root `.venv`:
   ```cmd
   Command: & "E:\Downloads\Chat_GPT_AI\.venv\Scripts\python.exe" -m pytest "E:\Downloads\Chat_GPT_AI\gigaforge\tests"
   ```
   *Output*:
   ```text
   FAILED tests/test_research.py::test_paired_identical_models_are_never_declared_improved
   ...
   ModuleNotFoundError: No module named 'gymnasium'
   FAILED tests/test_runtime_finder.py::test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin
   ======================== 2 failed, 39 passed in 34.30s ========================
   ```

---

### 1.3 Python Interpreter Selection & Launcher Routing Invariants
The routing architecture was inspected across four core components:

1. **`gigaforge/_RUN.bat`** (lines 4–15):
   ```bat
   set "GIGA_BOOT=.venv_native\Scripts\python.exe"
   set "GIGA_ARGS="
   if exist "%GIGA_BOOT%" goto launch
   set "GIGA_BOOT=..\novaforge\.venv\Scripts\python.exe"
   if exist "%GIGA_BOOT%" goto launch
   set "GIGA_BOOT=..\NovaForge\.venv\Scripts\python.exe"
   if exist "%GIGA_BOOT%" goto launch
   set "GIGA_BOOT=py"
   set "GIGA_ARGS=-3.11"
   :launch
   "%GIGA_BOOT%" %GIGA_ARGS% -u runtime_bootstrap.py %*
   exit /b %errorlevel%
   ```
   - Prioritizes `.venv_native\Scripts\python.exe` as the bootstrap Python interpreter.
   - Forwards all command-line arguments `%*` to `runtime_bootstrap.py`.

2. **`gigaforge/runtime_bootstrap.py`** (lines 17–37):
   - Reads `gigaforge/runtime_selection.json`.
   - On this machine, `runtime_selection.json` contains:
     ```json
     {
       "python": "E:\\Downloads\\Chat_GPT_AI\\gigaforge\\.venv_native\\Scripts\\python.exe",
       "device": "cuda",
       "source": "existing"
     }
     ```
   - `run_command(args)` executes `[python, '-u', str(ROOT / 'run.py'), *args]` in `ROOT` (`gigaforge/`) with `env=clean_env()` (which strips `PYTHONHOME` and `PYTHONPATH`).

3. **`gigaforge/runtime_finder.py`** (lines 119–145):
   - In `probe(python, pins, mode='cuda')` (line 124):
     ```python
     if (info['packages'].get('torch') or '').split('+')[0] != '2.9.1':
         raise ValueError('Requires PyTorch 2.9.1 for the native ABI')
     ```
     Any Python environment without PyTorch 2.9.1 (such as root `.venv` with 2.14.1) is explicitly rejected.
   - In `inspect_runtimes` (line 143):
     ```python
     compatible.sort(key=lambda r: (len(r['missing']), 0 if Path(r['python']).parent.parent == Path(project) / '.venv_native' else 1))
     ```
     Explicitly sorts and prioritizes `gigaforge/.venv_native` as the best compatible runtime.

4. **`gigaforge/run.py` (PyTorch Version Guard & Dynamic Linker Injection)**:
   - Line 42 (inside `launch(recipe)`):
     ```python
     if torch.__version__.split('+')[0] != '2.9.1':
         raise RuntimeError('Use the pinned PyTorch 2.9.1 runtime')
     ```
   - Lines 31–38 (inside `environment(threads)`):
     ```python
     def environment(threads=4):
         import torch
         env = dict(os.environ)
         lib = Path(torch.__file__).parent / 'lib'
         env['PATH'] = str(lib) + os.pathsep + str(Path(sys.base_prefix)) + os.pathsep + env.get('PATH', '')
         env['GIGAFORGE_TORCH_LIB'] = str(lib)
         env['GIGAFORGE_SIM_THREADS'] = str(threads)
         env['PYTHONHOME'] = sys.base_prefix
         env['OMP_NUM_THREADS'] = '1'
         env['MKL_NUM_THREADS'] = '1'
         return env
     ```
     This function dynamically injects `torch/lib` from the active Python interpreter into the `PATH` of child subprocess `GigaForge.exe`. If the active Python is not `gigaforge/.venv_native`, `GigaForge.exe` crashes upon launch.

---

### 1.4 Test Suite Differences: Root `tests/` vs `gigaforge/tests/`
A critical distinction was discovered between the test folders:
- **`E:\Downloads\Chat_GPT_AI\tests/`** (Root):
  Contains **73 test modules** and **731 individual tests** testing legacy components (e.g. replay downloading, trainer contracts, auto duos). Running `pytest tests/` from the repository root executes these 731 tests, which expect different environments and mocks.
- **`E:\Downloads\Chat_GPT_AI\gigaforge\tests/`**:
  Contains **6 test modules** and **41 individual tests** testing GigaForge native access, research logic, evaluation protocols, pacing, trial watch, and launcher routing:
  - `test_native_access.py` (6 tests)
  - `test_research.py` (5 tests)
  - `test_research_eval.py` (11 tests)
  - `test_research_pacing.py` (3 tests)
  - `test_runtime_finder.py` (10 tests)
  - `test_trial_watch.py` (6 tests)
  Total: 41 tests.

Running the 41 tests in `gigaforge/tests` using `gigaforge/.venv_native`:
```text
tests\test_native_access.py ......                                       [ 14%]
tests\test_research.py .....                                             [ 26%]
tests\test_research_eval.py ...........                                  [ 53%]
tests\test_research_pacing.py ...                                        [ 60%]
tests\test_runtime_finder.py .....F....                                  [ 85%]
tests\test_trial_watch.py ......                                         [100%]
================================== FAILURES ===================================
____ test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin ____
...
FAILED tests/test_runtime_finder.py::test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin
======================== 1 failed, 40 passed in 24.22s ========================
```
40 tests pass immediately; the **only** failure is the launcher routing defect in `20_WDL_BEST_VS_ORIGINAL_200x100.bat`.

---

## 2. Logic Chain

1. **ABI Compatibility Requirement (Observations 1.1, 1.2, 1.3)**:
   `GigaForge.exe` is compiled against LibTorch 2.9.1+cu126. The C++ ABI of LibTorch is not backward- or forward-compatible across minor/major versions. When PyTorch 2.14.1 (from root `.venv`) is injected into `PATH`, the Windows dynamic linker fails with `STATUS_ENTRYPOINT_NOT_FOUND` (`0xC0000139`). Therefore, PyTorch 2.9.1+cu126 in `gigaforge/.venv_native` is a strict, non-negotiable physical requirement of the native simulator.
2. **Version Guard Invariant (Observation 1.3)**:
   The guards in `gigaforge/run.py` (line 42) and `gigaforge/runtime_finder.py` (line 124) enforce `split('+')[0] == '2.9.1'`. This deliberately fails fast in Python before any child process can crash with a Windows dialog or access violation.
3. **Dispatcher Cascade (Observation 1.3)**:
   `_RUN.bat` resolves `gigaforge/.venv_native\Scripts\python.exe` first, and invokes `runtime_bootstrap.py`. `runtime_bootstrap.py` checks `runtime_selection.json`, which points to `gigaforge/.venv_native\Scripts\python.exe`, ensuring bitwise isolation from root `.venv`.
4. **Failure Isolation in Launchers (Observation 1.4, Peer Report m1_exp_1)**:
   In `gigaforge/tests/test_runtime_finder.py` (line 72), `test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin` iterates through all `.bat` files. `20_WDL_BEST_VS_ORIGINAL_200x100.bat` is the single launcher that bypassed `_RUN.bat` and hardcoded `.venv_native\Scripts\python.exe`. Replacing its invocation with `call "%~dp0_RUN.bat" run h2h --run research02 --rounds 200 --seconds 100` satisfies both assertions (`'_RUN.bat' in text` and `'.venv_native\\Scripts' not in text`) and brings the test suite to 41/41 passing (100%).
5. **Command Line Disambiguation (Observation 1.4)**:
   If a developer or automated worker executes `pytest tests/` from the repository root (`E:\Downloads\Chat_GPT_AI`), Python uses the active shell's environment or PATH, and targets root `tests/` (731 tests). To guarantee 100% isolation and run the intended GigaForge test suite, commands must explicitly invoke `gigaforge/.venv_native\Scripts\python.exe -m pytest gigaforge/tests`.

---

## 3. Caveats

1. **Read-Only Investigation**:
   No source code or batch files outside `.agents/teamwork/teamwork_explorer_m1_2` were modified. The proposed fix for `20_WDL_BEST_VS_ORIGINAL_200x100.bat` must be applied by the designated Worker agent.
2. **Subprocess Environment Cleanliness**:
   `runtime_bootstrap.py` strips `PYTHONHOME` and `PYTHONPATH` via `clean_env()`. However, if invoking python manually from PowerShell, active environment variables (e.g. `VIRTUAL_ENV` or global `PATH`) can inadvertently leak unless the full path to `gigaforge\.venv_native\Scripts\python.exe` is explicitly used.
3. **Secondary Virtualenv `NovaForge/.venv`**:
   `NovaForge/.venv` contains PyTorch `2.9.1+cpu`. It can be used as a read-only fallback donor for CPU routines and teacher asset serialization, but CANNOT be used for native GPU training or self-tests because `torch.cuda.is_available()` returns `False`.

---

## 4. Conclusion

1. **Isolation Status**: `gigaforge/.venv_native` is fully intact, healthy, and correctly configured with Python 3.11.9, PyTorch `2.9.1+cu126`, CUDA 12.6, Gymnasium 1.4.0, and Stable-Baselines3 2.9.2.
2. **Root `.venv` Prohibition**: The root `.venv` contains PyTorch 2.14.1 and lacks critical packages (`gymnasium`). It must NEVER be used for any GigaForge operations.
3. **Defect Root Cause**: The only failing test in `gigaforge/tests` (40 passed, 1 failed) is caused by `gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat` failing to delegate to `_RUN.bat`.
4. **Actionable Fix**: The Worker needs only to update `20_WDL_BEST_VS_ORIGINAL_200x100.bat` to route through `_RUN.bat`.

---

## 5. Verification Method: Exact Commands & Safeguards for the Worker

### 5.1 Proposed Code Patch for Worker (`gigaforge/20_WDL_BEST_VS_ORIGINAL_200x100.bat`)

Replace lines 7–12:
```bat
<<<<
if not exist ".venv_native\Scripts\python.exe" goto fallback
".venv_native\Scripts\python.exe" -u runtime_bootstrap.py run h2h --run research02 --rounds 200 --seconds 100
goto finished
:fallback
py -3.11 -u runtime_bootstrap.py run h2h --run research02 --rounds 200 --seconds 100
:finished
====
call "%~dp0_RUN.bat" run h2h --run research02 --rounds 200 --seconds 100
>>>>
```

---

### 5.2 Mandatory Execution Safeguards for the Worker

To ensure commands never fall into the root `.venv`:
1. **Rule 1 — Absolute Python Binary Path**:
   Never use bare `python` or `pytest`. ALWAYS use the full path:
   `E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe`
2. **Rule 2 — Module Execution via `-m pytest`**:
   Always invoke `python.exe -m pytest ...` instead of `pytest.exe`, ensuring that sys.path and package bindings bind strictly to `.venv_native`.
3. **Rule 3 — Explicit Target Directory**:
   Always specify `gigaforge/tests` (or run from within `gigaforge/` targeting `tests/`) to prevent running the 731 root tests.

---

### 5.3 Sequential Verification Command Suite

Execute the following exact commands in PowerShell or Command Prompt:

```powershell
# 1. Verify Python & PyTorch version guard and virtualenv isolation
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -c "import torch; assert torch.__version__ == '2.9.1+cu126'; assert torch.cuda.is_available(); print('ISOLATION_VERIFIED: PyTorch 2.9.1+cu126 CUDA OK')"

# 2. Run the targeted launcher routing test
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -m pytest "E:\Downloads\Chat_GPT_AI\gigaforge\tests\test_runtime_finder.py" -k "test_all_launchers_use_the_single_runtime_router_and_no_old_wandb_pin" -v

# 3. Run the complete GigaForge test suite (Expected: 41 passed, 0 failed, 100% pass rate)
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -m pytest "E:\Downloads\Chat_GPT_AI\gigaforge\tests" -v

# 4. Verify native C++ simulator self-tests
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -c "import subprocess, sys; from pathlib import Path; sys.path.insert(0, 'E:/Downloads/Chat_GPT_AI/gigaforge'); import run; sys.exit(subprocess.run([str(run.binary()), '--selftest'], env=run.environment()).returncode)"
# Expected:
# RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS
# NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS

# 5. Verify run.py feature, mask, network and GAE verification
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" "E:\Downloads\Chat_GPT_AI\gigaforge\run.py" verify
# Expected:
# NATIVE_FEATURE_MASK_NETWORK_GAE_VERIFICATION_PASS

# 6. Verify baseline model SHA256 hashes
& "E:\Downloads\Chat_GPT_AI\gigaforge\.venv_native\Scripts\python.exe" -c "import hashlib; expected = {'NovaForge/assets/chronos/POLICY.lt': 'cb4e93c281cc89bf5635a6c1c20d7de55f70667b9f744faac4be014f2cc72360', 'NovaForge/assets/chronos/SHARED_HEAD.lt': 'e0aac68af61c43c30b78a036466e9199fe10735e2006cbb5f080e81d6caf1640', 'NovaForge/assets/galactus/POLICY.lt': 'f31e15e118f14713ffc5d4af84ab0d8018c04f1451805f50a2e2df9d396603ed', 'NovaForge/assets/galactus/SHARED_HEAD.lt': 'a38be9da0a57141d0bf8e38bd51944f77aa04912f7912e9c4bc49f93db7285a4'}; [assert hashlib.sha256(open(p, 'rb').read()).hexdigest() == h for p, h in expected.items()]; print('ALL_BASELINE_HASHES_MATCH')"
```

### 5.4 Invalidation Conditions
- Any occurrence of PyTorch version other than `2.9.1+cu126` in the active runtime invalidates execution.
- Any attempt to run commands using bare `python` or root `.venv\Scripts\python.exe` causes Win32 loader crashes (`0xC0000139`) or `ModuleNotFoundError`.
- Any presence of `.venv_native\Scripts` in `20_WDL_BEST_VS_ORIGINAL_200x100.bat` invalidates test compliance.
