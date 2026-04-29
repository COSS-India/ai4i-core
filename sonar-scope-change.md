# SonarQube Scope Configuration — Change Summary

**Repo:** `COSS-India/ai4i-core`
**Branch:** `chore/sonar-scope-config`
**Change:** Add `sonar-project.properties` at repo root to scope analysis to actual application code.

---

## 1. What changed

**One file added** at the repo root: `sonar-project.properties`.

No other files modified. No Jenkins job changes. No CI/CD changes.

The Jenkins `sonarqube-scan` job auto-detects this file on every future scan.

---

## 2. Why

Before this change, SonarQube scanned the entire repo with default settings. That meant:

- `node_modules/`, `dist/`, `.next/`, build artifacts inflated the issue count
- TypeScript ran without `tsconfig.json` → type-aware rules silently disabled
- Python version not declared → some version-specific rules skipped
- Test files counted as production code → coverage % meaningless
- Non-code folders (`docs/`, `infrastructure/`, `scripts/`, `specs/`) added noise

This change fixes all five.

---

## 3. Scope — what's in, what's out

| Folder | Status | Analyzer |
|---|---|---|
| `services/` | **Source** | Python |
| `libs/` | **Source** | Python |
| `frontend/simple-ui/` | **Source** | TypeScript / React |
| `tests/` | **Tests** | Python (root-level integration & e2e) |
| `services/**/tests/`, `libs/**/tests/` | **Tests** | Python |
| `frontend/simple-ui/__tests__/` | **Tests** | TypeScript (Jest) |
| `docs/`, `specs/`, `infrastructure/`, `scripts/`, `.cursor/` | Not analyzed | — |
| `node_modules/`, `dist/`, `build/`, `.next/`, `__pycache__/`, `venv/` | Excluded | — |
| `migrations/`, `*.min.js`, `package-lock*.json` | Excluded | — |
| `frontend/simple-ui/test-asr-stream.js`, `test_audio.wav` | Excluded (manual artifacts) | — |

---

## 4. The file added — `sonar-project.properties`

```properties
sonar.projectKey=ai4i-core
sonar.projectName=ai4i-core

sonar.sources=services,libs,frontend/simple-ui
sonar.tests=tests,services,libs,frontend/simple-ui
sonar.test.inclusions=\
    tests/**,\
    services/**/tests/**,services/**/test_*.py,services/**/*_test.py,\
    libs/**/tests/**,libs/**/test_*.py,libs/**/*_test.py,\
    frontend/simple-ui/__tests__/**,\
    frontend/simple-ui/**/*.test.ts,frontend/simple-ui/**/*.test.tsx,\
    frontend/simple-ui/**/*.spec.ts,frontend/simple-ui/**/*.spec.tsx

sonar.exclusions=\
    **/node_modules/**,\
    **/dist/**,\
    **/build/**,\
    **/.next/**,\
    **/__pycache__/**,\
    **/*.min.js,\
    **/migrations/**,\
    **/venv/**,**/.venv/**,\
    frontend/simple-ui/test-asr-stream.js,\
    frontend/simple-ui/test_audio.wav,\
    **/package-lock*.json

sonar.python.version=3.10, 3.11
sonar.typescript.tsconfigPath=frontend/simple-ui/tsconfig.json
```

---

## 5. Key property reference

| Property | Value | Purpose |
|---|---|---|
| `sonar.projectKey` | `ai4i-core` | Project identifier in SonarQube dashboard |
| `sonar.sources` | `services,libs,frontend/simple-ui` | Folders treated as production code |
| `sonar.tests` | `tests,services,libs,frontend/simple-ui` | Folders that may contain tests (further filtered by `test.inclusions`) |
| `sonar.test.inclusions` | Patterns above | Files inside `sonar.tests` that are actually tests |
| `sonar.exclusions` | Patterns above | Files removed from analysis entirely |
| `sonar.python.version` | `3.10, 3.11` | Lowest is 3.10 (some libs require 3.11) — Sonar checks compat with both |
| `sonar.typescript.tsconfigPath` | `frontend/simple-ui/tsconfig.json` | Enables type-aware TS rules |

---

## 6. How language detection works (no per-folder mapping needed)

SonarQube routes each file to the correct analyzer **by file extension**:

- `.py` → Python analyzer (FastAPI-aware rules included)
- `.ts`, `.tsx` → TypeScript analyzer (type-aware when `tsconfig` is set)
- `.js`, `.jsx` → JavaScript analyzer
- `.css`, `.scss`, `.html` → respective analyzers

We do **not** declare "this folder is Python." We only declare **boundaries** (which folders) and **per-language hints** (`python.version`, `tsconfigPath`).

---

## 7. Verification

After the next Jenkins scan, the dashboard at
`http://13.201.212.216:9000/dashboard?id=ai4i-core` should show:

- **Code tab** lists only `services/`, `libs/`, `frontend/simple-ui/`
- **Lines of Code** breakdown contains both **Python** and **TypeScript**
- `tests/` is labeled "Test sources," not "Main sources"
- Total LOC and issue count are noticeably lower than the previous scan

---

## 8. Rollback

To revert: delete `sonar-project.properties` from the repo root. SonarQube falls back to default behavior on the next scan.

---

## 9. Future improvements (not part of this change)

1. **Test coverage** — wire `pytest --cov` and `jest --coverage` outputs:
   ```
   sonar.python.coverage.reportPaths=...coverage.xml
   sonar.javascript.lcov.reportPaths=frontend/simple-ui/coverage/lcov.info
   ```
2. **Separate Quality Gates** — split into `ai4i-core-portal` and `ai4i-core-api` projects if frontend and backend teams need independent pass/fail.
