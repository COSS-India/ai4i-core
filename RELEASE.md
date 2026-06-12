# Release Guide

This document describes the release process for **AI4I-Core** — how new versions are
branched, versioned, tested, tagged, and published. AI4I-Core is an open-source platform and every release is a public commitment to
stability. This guide covers the full lifecycle: from opening a feature branch to
publishing the shared library on PyPI and cutting a GitHub Release.

---

## Table of Contents

- [Release Cadence](#release-cadence)
- [Roles and Responsibilities](#roles-and-responsibilities)
- [Versioning Scheme](#versioning-scheme)
- [Branch Strategy](#branch-strategy)
- [Step-by-Step: Cutting a Release](#step-by-step-cutting-a-release)
- [Release Artifacts](#release-artifacts)
- [Hotfix Releases](#hotfix-releases)
- [Post-Release Checklist](#post-release-checklist)

---

## Release Cadence

AI4I-Core follows a **milestone-driven release cadence**. A new minor or major release is
cut when a planned set of features and fixes is complete and stable. Patch releases are cut as needed to address critical bugs or security
vulnerabilities.

| Release type | Trigger | Example |
|---|---|---|
| **Major** (`vX.0.0`) | Significant architectural change or breaking API change | v2.0.0 → v3.0.0 |
| **Minor** (`vX.Y.0`) | New features, non-breaking changes | v2.1.0 → v2.2.0 |
| **Patch** (`vX.Y.Z`) | Bug fixes, security patches, dependency updates | v2.2.0 → v2.2.1 |


---

## Roles and Responsibilities

| Role | Responsibility |
|---|---|
| **Release Manager** (project lead / designated maintainer) | Initiates and owns the release: creates the release branch, coordinates version bumps, creates the Git tag, and publishes the PyPI package |
| **Contributors** | Ensure their merged work is covered by tests; update `CHANGELOG.md` entries in their PRs |
| **Maintainers** | Review and approve release PRs at each promotion stage (`release-X.Y` → `dev`, `dev` → `staging`, `staging` → `master`) |

---

## Versioning Scheme

AI4I-Core uses **Semantic Versioning** ([SemVer](https://semver.org/)) — `MAJOR.MINOR.PATCH`.

The project has a single version tracked via Git tags. The only separately versioned
artifact is the shared Python library published to PyPI.

| Artifact | File to update | Notes |
|---|---|---|
| **Platform (overall)** | Git tag (e.g. `v2.2.0`) | Canonical version reference for the whole project |
| **Shared library (`ai4icore-core`)** | [libs/ai4icore_core/pyproject.toml](./libs/ai4icore_core/pyproject.toml) — `version` | Published independently to PyPI; bump only when the library changes |

> All future Git tags must follow the `vMAJOR.MINOR.PATCH` format.

---

## Branch Strategy

The project uses the following branching model:

```
master          ← production; every commit here is a release
  ↑
staging         ← pre-production QA; verified before merging to master
  ↑
dev             ← stabilisation branch; release branch merges here first
  ↑
release-X.Y     ← feature integration; all feature branches merge here
  ↑
feature/...     ← individual feature or fix branches
```

### Rules

- **`master`** is always production-ready. Direct commits are not allowed except for
  emergency hotfixes (see [Hotfix Releases](#hotfix-releases)).
- **`staging`** mirrors production. Changes are validated here before going to `master`.
- **`dev`** is the stabilisation branch. Once a `release-X.Y` branch is feature-complete
  and stabilised, it is merged into `dev`.
- **`release-X.Y`** is the active integration branch for a milestone. Feature PRs target
  this branch. Name it `release-MAJOR.MINOR` (e.g. `release-2.2`).
- Once `dev` is stable it is promoted to `staging`, then to `master` and tagged.

---

## Step-by-Step: Cutting a Release

### 1. Create the release branch

Cut the release branch from the current `dev` (or from `master` if starting fresh):

```bash
git checkout dev
git pull origin dev
git checkout -b release-X.Y
git push -u origin release-X.Y
```

Feature PRs for this milestone are now opened against `release-X.Y`.

### 2. Update CHANGELOG.md

Add a new section at the top of [CHANGELOG.md](./CHANGELOG.md) for this release following
the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format:

```markdown
## [2.3.0] - YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Fixed
- ...
```

Commit:

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for v2.3.0"
```

### 3. Merge release branch into dev

Once the release branch is feature-complete and stabilised, open a PR from
`release-X.Y` → `dev`. At least one maintainer must review and approve.

```bash
git checkout dev
git pull origin dev
git merge --no-ff release-X.Y
git push origin dev
```

### 4. Run tests before promoting

Refer to [docs/SETUP_GUIDE.md](./docs/SETUP_GUIDE.md) for environment setup. Ensure all
services are running and verify there are no failures before promoting to staging:

- **auth-service** — authentication, users, tenants, RBAC
- **platform-core-service** — model registry, alerts, telemetry
- **inference-service** — unified inference over Triton / OpenAI-compatible backends
- **simple-ui** — frontend

### 5. Promote dev → staging

Open a PR from `dev` → `staging`. After review and approval:

```bash
git checkout staging
git pull origin staging
git merge --no-ff dev
git push origin staging
```

Perform smoke tests and any manual QA on the staging environment.

### 6. Promote staging → master

Once staging is verified, open a PR from `staging` → `master`. After approval:

```bash
git checkout master
git pull origin master
git merge --no-ff staging
git push origin master
```

### 7. Tag the release

Create an annotated tag on `master`:

```bash
git checkout master
git pull origin master
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

Tag format is strictly `vMAJOR.MINOR.PATCH`. Do not use bare versions (`2.0`) or
pre-release suffixes (`v0.4-dev`).

### 8. Publish the shared library to PyPI

Only needed if `libs/ai4icore_core` has changed. Before building, ensure the `version`
field in [libs/ai4icore_core/pyproject.toml](./libs/ai4icore_core/pyproject.toml) is
updated to the new version.

```bash
cd libs/ai4icore_core
python -m build
twine upload dist/*
```

Verify the new version appears on [PyPI](https://pypi.org/project/ai4icore-core/).

### 9. Create a GitHub Release

On GitHub, go to **Releases → Draft a new release**:

- **Tag:** select the tag you just pushed (e.g. `v2.3.0`)
- **Title:** `v2.3.0`
- **Body:** paste the CHANGELOG entry for this version
- Attach any release artifacts if applicable

Publish the release.

### 10. Sync staging with master

After tagging, bring `staging` up to date with `master` to keep them in sync:

```bash
git checkout staging
git pull origin staging
git merge --no-ff master
git push origin staging
```

---

## Release Artifacts

| Artifact | Location | Published by |
|---|---|---|
| Python shared library (`ai4icore-core`) | [PyPI: ai4icore-core](https://pypi.org/project/ai4icore-core/) | Release manager via `twine upload` |
| Source tarball / release notes | [GitHub Releases](https://github.com/COSS-India/ai4i-core/releases) | Auto-generated on tag; release notes added manually |

> The application services (auth, platform-core, inference, frontend) are not published to
> a container registry as part of this project's release. Deployers build Docker images
> locally from the tagged source using the Dockerfiles provided in each service directory.

---

## Hotfix Releases

For critical bugs or security vulnerabilities discovered:

1. Branch off `master` (not `dev`):
   ```bash
   git checkout master
   git checkout -b hotfix/vX.Y.Z-description
   ```
2. Apply the minimal fix.
3. Bump the patch version in all component files.
4. Update `CHANGELOG.md`.
5. Open a PR directly to `master`, get at least one review, and merge.
6. Tag `vX.Y.Z` on `master` and publish following steps 7–9 above.
7. Back-merge `master` into `staging` and `dev` to keep branches in sync:
   ```bash
   git checkout staging && git merge --no-ff master && git push origin staging
   git checkout dev && git merge --no-ff master && git push origin dev
   ```

---

## Post-Release Checklist

Use this checklist when cutting every release:

- [ ] Release branch `release-X.Y` created; feature PRs merged into it
- [ ] All component versions bumped to `vX.Y.Z`
- [ ] `CHANGELOG.md` updated with the new section
- [ ] `release-X.Y` merged into `dev`
- [ ] All tests pass (`pytest`, `npm test`, `npm run build`)
- [ ] `dev` promoted to `staging`; smoke tests pass on staging environment
- [ ] `staging` promoted to `master` via reviewed PR
- [ ] Annotated Git tag `vX.Y.Z` pushed to origin
- [ ] `ai4icore-core` published to PyPI (if the shared library changed)
- [ ] GitHub Release created with release notes
- [ ] `staging` synced with `master`