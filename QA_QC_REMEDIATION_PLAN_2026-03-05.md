# QA/QC Audit and Remediation Plan

Date: 2026-03-05
Repository: osx-system-agent

## Scope
- Automated validation (lint, tests, coverage, static/type tooling status)
- Targeted manual code review of runtime-critical and destructive paths
- Remediation planning with sequencing and acceptance criteria

## QA Execution Summary

### Commands executed
- `ruff check .`
- `pytest -k 'not history' --cov=src/osx_system_agent --cov-report=term-missing`
- `pytest tests/test_history.py -k 'not test_records_snapshot and not test_appends_multiple'`
- targeted timeout repro for `tests/test_history.py::TestRecordSnapshot::test_records_snapshot`
- runtime repro for `scan_large_files` on nested directories
- mypy import/runtime sanity check

### Results
- Lint: pass (`ruff check .`)
- Tests (excluding known blockers): `300 passed, 7 deselected`
- Coverage (same run): total `60%`
- Blocker test: `test_records_snapshot` timed out after 15s (non-deterministic/slow integration behavior in unit test)
- Type-check toolchain: `mypy` unusable in current venv due binary extension import error on Python `3.14.0a2`

## Findings (Prioritized)

### 1) Critical: `scan_large_files` crashes on directories (runtime TypeError)
- Evidence:
  - `src/osx_system_agent/scanners/large_files.py:46` calls `should_exclude(Path(dirpath) / d, exclude_patterns)`
  - `should_exclude` requires `(path, root, patterns)`
  - Repro produced: `TypeError: should_exclude() missing 1 required positional argument: 'patterns'`
- Impact:
  - `osa scan large-files` fails on realistic trees containing subdirectories.
  - Existing tests miss this because they mostly use flat temp dirs.
- Root cause:
  - API contract mismatch between `large_files.py` and `filters.py`.

### 2) Critical: Test suite includes hanging/non-isolated history snapshot tests
- Evidence:
  - `tests/test_history.py:15-35` calls `record_snapshot()` without mocking heavy dependencies.
  - `record_snapshot()` in `src/osx_system_agent/reports/history.py:26-28` executes real `scan_caches(min_size=0)` and `scan_disk_hogs(min_size=0)`.
  - Targeted run timed out after 15s.
- Impact:
  - Full CI/local test runs are unreliable and can stall.
  - Unit tests depend on host filesystem size/state.
- Root cause:
  - Integration behavior embedded in unit tests; no dependency injection/mocking for expensive scanners.

### 3) High: Cache cleanup can recursively delete broad/system targets
- Evidence:
  - `src/osx_system_agent/scanners/caches.py:31` includes `"/Library/Caches"` in default targets.
  - `src/osx_system_agent/clean/caches.py:43-44` performs `shutil.rmtree(entry.path)` then recreates directory.
- Impact:
  - Potential destructive behavior if run with elevated permissions.
  - Blast radius includes system cache directories.
- Root cause:
  - No safety guardrails (ownership checks, protected path policy, explicit opt-in for system paths).

### 4) Medium: Scheduler binary discovery has environment-specific hardcoding
- Evidence:
  - `src/osx_system_agent/schedule.py:22` hardcodes `~/Documents/GitHub/osx-system-agent/.venv/bin/osa`.
- Impact:
  - Portability and install reliability issues outside this workstation/repo layout.
- Root cause:
  - Local path assumptions in runtime code.

### 5) Medium: HTML report branding path is environment-specific
- Evidence:
  - `src/osx_system_agent/reports/html.py:20-25` hardcodes a OneDrive team path for logo asset.
- Impact:
  - Non-portable branding behavior; inconsistent output across machines.
- Root cause:
  - Embedded organization-specific asset path in shared code.

### 6) Medium: Type-check quality gate is currently non-functional
- Evidence:
  - Import error from `mypy` binary extension in current venv (`_PyLongWriter_Create` missing).
- Impact:
  - No effective static type gate despite mypy configuration in `pyproject.toml`.
- Root cause:
  - Toolchain/environment mismatch (Python pre-release runtime vs installed mypy artifact).

### 7) Medium: Coverage gaps in high-risk modules
- Evidence from coverage run:
  - `src/osx_system_agent/cli.py` 19%
  - `src/osx_system_agent/clean/caches.py` 0%
  - `src/osx_system_agent/reports/consolidated.py` 0%
  - `src/osx_system_agent/reports/markdown.py` 0%
  - `src/osx_system_agent/scanners/login_items.py` 24%
- Impact:
  - Regressions likely in user-facing command paths and destructive operations.
- Root cause:
  - Test focus is uneven; limited integration coverage for command/report workflows.

## Remediation Plan

## Phase 0 (Immediate: block regressions)
1. Fix `scan_large_files` exclusion call signature and add regression tests with nested directories.
2. Split history tests:
- Unit tests fully mock `get_system_status`, `scan_caches`, `scan_disk_hogs`.
- Integration test (if kept) marked slow and excluded from default run.
3. Add CI timeout/guard for tests to fail fast on hangs.

Acceptance criteria:
- `osa scan large-files` succeeds on nested directory fixtures.
- `pytest` default run completes deterministically in CI.

## Phase 1 (Safety hardening)
1. Restrict cache cleanup defaults to user-space paths only.
2. Add explicit `--include-system` or similar opt-in for system cache paths.
3. Add path safety checks before deletion:
- Reject root-level/protected paths unless explicitly forced.
- Require ownership/write checks and log explicit warnings.
4. Add tests for destructive-path guardrails.

Acceptance criteria:
- System paths are not deleted in default mode.
- Safety checks are unit-tested and enforced in CLI and library entrypoints.

## Phase 2 (Portability/configurability)
1. Replace hardcoded `osa` resolution with robust strategy:
- prefer `shutil.which("osa")`
- fallback to `sys.executable -m osx_system_agent.cli` if script missing.
2. Move HTML logo path/theme to config/env/CLI option; keep default generic branding.
3. Add portability tests for schedule/report generation with temporary environments.

Acceptance criteria:
- Schedule/report generation works across machines without repo-specific paths.

## Phase 3 (Quality gates and coverage uplift)
1. Standardize supported Python versions (recommend 3.11-3.13 stable in CI).
2. Restore type-check gate:
- either stable mypy on supported Python
- or alternate checker if needed.
3. Raise coverage thresholds incrementally, prioritizing:
- `cli.py`
- `clean/caches.py`
- `reports/consolidated.py`
- `reports/markdown.py`
- `scanners/login_items.py`
4. Add end-to-end smoke tests for critical CLI commands.

Acceptance criteria:
- Type-check job passes in CI.
- Total coverage >75% with targeted module minimums.

## Suggested Work Breakdown
- Sprint A (1-2 days): Phase 0
- Sprint B (2-3 days): Phase 1
- Sprint C (1-2 days): Phase 2
- Sprint D (2-3 days): Phase 3

## Residual Risk if Deferred
- Runtime command failures in production (`large-files` path traversal)
- Continued non-deterministic CI/test behavior
- Potentially unsafe cleanup behavior on privileged execution
- Ongoing blind spots due missing type and coverage gates
