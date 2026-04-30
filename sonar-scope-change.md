# SonarQube Scope Configuration — Change Summary

**Repo:** `COSS-India/ai4i-core`
**Branch:** `chore/sonar-scope-config`
**Change:** Add `sonar-project.properties` at repo root to scope analysis to actual application code.

---

## 1. What changed

Two changes, both required for scoping to take effect:

1. **One file added** at the repo root: `sonar-project.properties` (in `ai4i-core`, branch `chore/sonar-scope-config`).
2. **Jenkins `sonarqube-scan` pipeline updated** — the `SonarQube Analysis` stage now uses the repo's `sonar-project.properties` when present, falling back to the previous default behavior when absent. Without this, the pipeline silently overwrites the repo's file at build time and the scoping has no effect.

After both, every future scan auto-detects the repo's properties file.

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

### 3.1 Top-level folders in `ai4i-core`

| Folder | Scanned? | Treated as | Reason |
|---|---|---|---|
| `services/` | Yes | **Main source** (Python + Dockerfiles + YAML + JSON) | In `sonar.sources` |
| `libs/` | Yes | **Main source** (Python) | In `sonar.sources` |
| `frontend/simple-ui/` | Yes | **Main source** (TS / JS / CSS / HTML + Dockerfile) | In `sonar.sources` |
| `tests/` | Yes | **Tests** (Python integration & e2e) | In `sonar.tests` + matches `tests/**` test inclusion |
| `infrastructure/` | No | — | Not in `sonar.sources` |
| `docs/` | No | — | Not in `sonar.sources` |
| `scripts/` | No | — | Not in `sonar.sources` |
| `specs/` | No | — | Not in `sonar.sources` |
| `.cursor/` | No | — | Not in `sonar.sources` |
| `.git/` | No | — | Always ignored by scanner |
| Root files (`README.md`, `CONTRIBUTING.md`, `QUICKSTART.md`, `LICENSE`, `docker-compose*.yml`, `package-lock.json`, `.gitignore`, `.gitattributes`, `.pre-commit-config.yaml`, `env.template`) | No | — | Not in `sonar.sources`; lockfiles also explicitly excluded |

### 3.2 Inside the four scanned folders

#### `services/` (e.g. `services/auth-service/`, `services/llm-service/`, …)

| Pattern | Classified as |
|---|---|
| `services/**/*.py` (excluding test patterns below) | Main source (Python) |
| `services/**/Dockerfile`, `services/**/Dockerfile.*` | Main source (Docker) |
| `services/**/*.yml`, `*.yaml`, `*.json` | Main source (YAML / JSON) |
| `services/**/*.html`, `*.css` | Main source (Web) |
| `services/**/tests/**`, `services/**/test_*.py`, `services/**/*_test.py` | **Tests** (Python) |
| `services/**/__pycache__/**`, `*.pyc`, `.venv/`, `venv/`, `migrations/`, `dist/`, `build/`, `node_modules/` | **Excluded** |

#### `libs/` (e.g. `libs/ai4icore_auth/`, `libs/ai4icore_logging/`, …)

| Pattern | Classified as |
|---|---|
| `libs/**/*.py` (excluding test patterns) | Main source (Python) |
| `libs/**/pyproject.toml`, `*.yml`, `*.json` | Main source |
| `libs/**/tests/**`, `libs/**/test_*.py`, `libs/**/*_test.py` | **Tests** (Python) |
| Same `__pycache__/`, `.venv/`, etc. | **Excluded** |

#### `frontend/simple-ui/`

| Pattern | Classified as |
|---|---|
| `frontend/simple-ui/src/**/*.{ts,tsx,js,jsx}` | Main source (TypeScript) |
| `frontend/simple-ui/src/**/*.css` | Main source (CSS) |
| `frontend/simple-ui/Dockerfile`, `Dockerfile.dev` | Main source (Docker) |
| `frontend/simple-ui/*.config.js` (next, jest) | Main source (JS) |
| `frontend/simple-ui/__tests__/**`, `**/*.test.{ts,tsx}`, `**/*.spec.{ts,tsx}` | **Tests** (TS) |
| `frontend/simple-ui/node_modules/`, `dist/`, `build/`, `.next/`, `*.min.js` | **Excluded** |
| `frontend/simple-ui/test-asr-stream.js`, `test_audio.wav`, `package-lock*.json` | **Excluded** (explicit) |

#### `tests/` (root-level)

| Pattern | Classified as |
|---|---|
| `tests/conftest.py`, `tests/pytest.ini`, `tests/requirements.txt` | **Tests** (Python) |
| `tests/integration/**/*.py` | **Tests** (Python) |
| `tests/e2e/**/*.py` | **Tests** (Python) |
| `tests/fixtures/**` | **Tests** |

> Everything under `tests/` is classified as test code, not main. That's why coverage % can be calculated against it later, and why test files get a slightly different rule set (e.g. SonarQube allows long functions in tests but not in production code).

### 3.3 Footprint observed in the latest scan (build #6)

| Metric (from Jenkins console) | Value | Means |
|---|---|---|
| Files indexed | **1,035** | Files SonarQube actually looked at |
| Files ignored by inclusion / exclusion patterns | 1,047 | What our scope kept out |
| Files ignored by SCM (`.gitignore`) | 15 | Local artifacts in checkout |
| Languages detected | **8** (css, docker, js, json, py, ts, web/HTML, yaml) | Found inside the scanned folders |
| Python source files analyzed | 692 | services + libs production code |
| TS / JS / CSS source files analyzed | 153 | frontend/simple-ui src |
| Dockerfiles analyzed (IaC sensor) | 29 | Inside `services/` and `frontend/simple-ui/` — **not** `infrastructure/` |
| Main source files reported to SCM | 794 | Excludes test files |

### 3.4 "Infrastructure-flavored" issues vs the `infrastructure/` folder

SonarQube categorizes Dockerfile and YAML findings under labels like *"Cloud-native"*, *"Infrastructure as Code"*, *"Container security"*. **The label refers to the rule, not the file path.** Those issues come from Dockerfiles inside `services/` and `frontend/simple-ui/` (29 of them), **not** from the repo's `infrastructure/` folder.

To prove it: in the SonarQube **Issues** tab, filter the file path by `infrastructure` → expected zero results. Filter by `Dockerfile` → hits in `services/<svc>/Dockerfile` and `frontend/simple-ui/Dockerfile`.

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

## 7. Verification (results from build #6 on `chore/sonar-scope-config`)

After the change was applied and the `sonarqube-scan` job re-run:

- Console output shows `----- Using repo's sonar-project.properties -----`
- Lines of Code dropped **114k → 98k** (infrastructure / docs / scripts / specs no longer scanned)
- Quality Gate flipped **Failed → Passed**
- Issues tab filtered by file path `infrastructure` → **zero results**
- **Code** tab in dashboard lists only `services/`, `libs/`, `frontend/simple-ui/`, `tests/`
- Both **Python** and **TypeScript** appear in the language breakdown
- `tests/` is labeled "Test sources," not "Main sources"

Dashboard: <http://13.201.212.216:9000/dashboard?id=ai4i-core>

---

## 8. Rollback

To revert: delete `sonar-project.properties` from the repo root and push. The Jenkins pipeline's `if [ -f sonar-project.properties ]` check falls through to the previously hard-coded `sonar.sources=.` default, restoring the pre-change behavior. (No Jenkins changes needed to roll back.)

---

## 9. Future improvements (not part of this change)

1. **Test coverage** — wire `pytest --cov` and `jest --coverage` outputs:
   ```
   sonar.python.coverage.reportPaths=...coverage.xml
   sonar.javascript.lcov.reportPaths=frontend/simple-ui/coverage/lcov.info
   ```
2. **Separate Quality Gates** — split into `ai4i-core-portal` and `ai4i-core-api` projects if frontend and backend teams need independent pass/fail.
