# ADR-66: Nanobot Pre-Phase 37 Security & Resilience Hardening

**Status**: Accepted  
**Date**: 2026-04-24  
**Method**: Harness 5-Stage Dialectic Workflow (Planner → Extreme Critic → V2 Planner → Validating Critic → Final Planner)  
**Files Affected**: `nanobot/agent/verification.py`, `nanobot/agent/tools/rpa_executor.py`, `nanobot/agent/loop.py`

---

## Context

A rigorous pre-Phase 37 architectural security audit identified 3 P0-level vulnerabilities and 3 P1-level defects in the Nanobot core layer. This ADR documents the decisions reached after a 5-round dialectic review process.

### Issues Addressed

| ID | Severity | Location | Issue |
|----|----------|----------|-------|
| V1 | P0 CAUTION | `verification.py` | L1 path defense lacks absolute path resolution — `../` traversal bypass |
| V2 | P0 CAUTION | `rpa_executor.py` | Out-of-bounds coordinates only generate a warning; physical click still executes |
| V3 | P0 WARNING | `rpa_executor.py` | Modifier sniffing cannot prevent destructive input via `type` action |
| D1 | P1 IMPORTANT | `loop.py` | `_detect_fuzzy_loop` uses brittle string splitting; exceptions silently swallowed |
| D2 | P1 IMPORTANT | `loop.py` | `_normalize_tool_result` blind truncation destroys JSON/Stacktrace continuity |
| D3 | P1 IMPORTANT | `verification.py` | `_check_rule_ssrs_fatal` hard-matches a quote-sensitive magic string |

---

## Decisions

### Decision 1 (V1): Layered Path Defense

**Rejected**: Applying `os.path.abspath()` to the full `exec` command string — this transforms a shell command into a garbage path and destroys the existing substring-based defense.

**Adopted**:
- `write_file` / `edit_file`: Use `os.path.realpath(os.path.expanduser(path)).lower()` — this resolves symlinks and junction points. Compare using `startswith()` against a pre-resolved `_SENSITIVE_PATHS_RESOLVED` set (computed once at module load).
- `exec`: Retain existing regex matching. No path resolution applied to shell command strings.
- Trailing `os.sep` is appended to all sensitive path entries before comparison (prevents `/etc/password_folder` from matching `/etc/pass`).

### Decision 2 (V2): RPA Bounds Checking — Decouple Stale from Out-of-Bounds

**Rejected**: Any `_check_bounds` return value triggers a hard block (Draft V1) — this locks all RPA operations after 60 seconds without a new screenshot.

**Adopted**: Refactor `_check_bounds` to return `tuple[bool, str | None]`:
- `(False, warning_str)`: Context is stale but coordinates are within bounds → **allow with warning prefix**
- `(True, error_str)`: Coordinates are physically outside the monitor boundary → **hard block; return Error immediately**

### Decision 3 (V3): RPA `type` Content Scanning — Architectural Boundary

**Rejected**: Adding regex content scanning to `evaluate_dynamic_tags` for the `type` action. At least 4 bypass vectors exist (split calls, clipboard paste, `press` keystroke-by-keystroke, Windows CMD caret escaping `p^o^w^e^r^s^h^e^l^l`). This would be security theater.

**Adopted**: Retain only the existing length check (`> 800 chars → SENSITIVE`). The ultimate defense boundary for GUI interaction is **physical Zone Containment** (ADR-64), not keystroke filtering. This decision is explicitly recorded to prevent future re-introduction of ineffective content regex scanning.

### Decision 4 (D2): 10/90 Pure-String Truncation

**Rejected**: Attempting `json.loads()` on oversized tool results — creates OOM risk and a logic bug where JSON branch output can exceed `max_chars`.

**Adopted**: Pure string split with tail-heavy ratio (stacktraces and error messages appear at the bottom of output):
- Head: 10% of `max_chars` (~1600 chars) — provides leading context
- Tail: 90% of `max_chars` (~14400 chars) — preserves the error chain

Python str slice operates on characters (not bytes), so multi-byte UTF-8 characters (e.g., CJK) are never split mid-character.

### Decision 5 (D1): Loop Detection Robustness

**Adopted**: Replace bare `json.loads()` with `json_repair.loads()` (already a project dependency). Change exception logging from `logger.debug` (invisible in production) to `logger.warning`.

### Decision 6 (D3): SSRS Fatal — Eliminate DOTALL

**Rejected**: `re.compile(r'error_type.*DependencyFatal', re.DOTALL)` — cross-line matching causes false positives (e.g., user asking about `DependencyFatal` in a chat message triggers rule).

**Adopted**: Three-tier regex cascade without DOTALL, matching within a single message content string only:
1. Exact JSON format: `"error_type"\s*:\s*"DependencyFatal"`
2. Loose variant: `error_type["\s:]+DependencyFatal`
3. Bare keyword: `\bDependencyFatal\b`

### Decision 7 (C8): Mandatory Adversarial Test Coverage

**Adopted**: Four new adversarial test files targeting the precise attack vectors identified in the audit:
- `tests/adversarial/test_path_traversal.py`
- `tests/adversarial/test_rpa_bounds.py`
- `tests/adversarial/test_truncation_safety.py`
- `tests/adversarial/test_ssrs_false_positive.py`

---

## Consequences

- **Backward Compatibility**: 100%. No changes to external tool APIs or return contracts.
- **Performance**: Net improvement — removal of `json.loads()` from the hot path in `_normalize_tool_result`.
- **New Dependencies**: None. `json_repair` and `os.path.realpath` are already available.
- **Deferred**: Full AST-based shell command parsing (Audit Section 3, architectural recommendation). Acknowledged but deferred — cost/benefit ratio is unfavorable at this scale. Mitigated by mandatory HITL routing for DESTRUCTIVE-tagged tools.
