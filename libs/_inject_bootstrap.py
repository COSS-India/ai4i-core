"""
Wire `ai4icore_bootstrap` into the 11 inference services that import it.

For each service:
  1. Dockerfile builder stage: insert
       COPY libs/ai4icore_bootstrap /app/libs/ai4icore_bootstrap
     immediately after the existing COPY of ai4icore_constants.
  2. Dockerfile builder stage: insert the matching pip install line right
     after the ai4icore_constants install (so dependency order is preserved:
     core -> exceptions -> constants -> bootstrap).
  3. Dockerfile runtime stage: insert COPY --from=builder line.
  4. docker-compose-local.yml: insert the volume mount immediately after the
     existing ai4icore_constants mount in each affected service block.

The script is idempotent: re-running on an already-wired service is a no-op.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SERVICES = [
    "asr-service",
    "nmt-service",
    "tts-service",
    "llm-service",
    "ner-service",
    "ocr-service",
    "language-detection-service",
    "language-diarization-service",
    "speaker-diarization-service",
    "transliteration-service",
    "audio-lang-detection-service",
]


# ── Dockerfile patcher ────────────────────────────────────────────────

def patch_dockerfile(svc: str) -> str:
    df = ROOT / "services" / svc / "Dockerfile"
    if not df.is_file():
        return "no Dockerfile"
    text = df.read_text(encoding="utf-8")
    if "ai4icore_bootstrap" in text:
        return "already references ai4icore_bootstrap"

    lines = text.splitlines(keepends=True)
    out = []
    builder_copy_done = False
    builder_pip_done = False
    runtime_copy_done = False

    # Discover the existing pip install flag style (--user, -e) from the
    # ai4icore_constants install line so the new bootstrap install matches.
    pip_flags = "--no-cache-dir --user"
    pip_editable = "-e"
    for ln in lines:
        m = re.match(
            r"^(\s*)RUN pip install (?P<flags>.*?) (?P<ed>-e )?/app/libs/ai4icore_constants\b",
            ln,
        )
        if m:
            pip_flags = m.group("flags").strip()
            pip_editable = (m.group("ed") or "").strip()
            break

    for ln in lines:
        # Builder COPY: place new line right AFTER ai4icore_constants COPY
        if (
            not builder_copy_done
            and re.match(r"^(\s*)COPY libs/ai4icore_constants\b", ln)
        ):
            out.append(ln)
            indent = re.match(r"^(\s*)", ln).group(1)
            out.append(f"{indent}COPY libs/ai4icore_bootstrap /app/libs/ai4icore_bootstrap\n")
            builder_copy_done = True
            continue

        # Builder pip install: place new line right AFTER ai4icore_constants install
        if (
            not builder_pip_done
            and re.match(r"^(\s*)RUN pip install .* /app/libs/ai4icore_constants\b", ln)
        ):
            out.append(ln)
            indent = re.match(r"^(\s*)", ln).group(1)
            ed = (pip_editable + " ") if pip_editable else ""
            out.append(
                f"{indent}RUN pip install {pip_flags} {ed}/app/libs/ai4icore_bootstrap\n"
            )
            builder_pip_done = True
            continue

        # Runtime COPY --from=builder: place new line right after the
        # ai4icore_constants runtime COPY
        if (
            not runtime_copy_done
            and re.match(r"^(\s*)COPY --from=builder /app/libs/ai4icore_constants\b", ln)
        ):
            out.append(ln)
            indent = re.match(r"^(\s*)", ln).group(1)
            out.append(
                f"{indent}COPY --from=builder /app/libs/ai4icore_bootstrap /app/libs/ai4icore_bootstrap\n"
            )
            runtime_copy_done = True
            continue

        out.append(ln)

    df.write_text("".join(out), encoding="utf-8")
    return (
        f"copy={builder_copy_done}, pip={builder_pip_done}, "
        f"runtime={runtime_copy_done}, flags='{pip_flags}', "
        f"editable={'yes' if pip_editable else 'no'}"
    )


# ── docker-compose-local.yml patcher ─────────────────────────────────

def patch_compose() -> str:
    cf = ROOT / "docker-compose-local.yml"
    text = cf.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out = []
    inserted_per_service: dict[str, bool] = {}

    # Track which service block we're currently inside (top-level "  <svc>:" line).
    current_service = None
    service_re = re.compile(r"^  ([a-zA-Z0-9_-]+):\s*$")

    for ln in lines:
        m = service_re.match(ln)
        if m and not ln.startswith("    "):
            current_service = m.group(1)

        # Inside an affected service: insert the bootstrap mount right after
        # the ai4icore_constants mount.
        if (
            current_service in SERVICES
            and not inserted_per_service.get(current_service)
            and re.match(
                r"^      - \./libs/ai4icore_constants:/app/libs/ai4icore_constants\s*$",
                ln,
            )
        ):
            out.append(ln)
            out.append(
                "      - ./libs/ai4icore_bootstrap:/app/libs/ai4icore_bootstrap\n"
            )
            inserted_per_service[current_service] = True
            continue

        out.append(ln)

    cf.write_text("".join(out), encoding="utf-8")
    inserted = [s for s, v in inserted_per_service.items() if v]
    missed = [s for s in SERVICES if s not in inserted]
    return f"inserted in {len(inserted)} services; missing constants-mount: {missed}"


# ── Driver ───────────────────────────────────────────────────────────

def main() -> None:
    print("== Dockerfile patches ==")
    for s in SERVICES:
        print(f"  [{s}] {patch_dockerfile(s)}")
    print("\n== docker-compose-local.yml patch ==")
    print(f"  {patch_compose()}")


if __name__ == "__main__":
    main()
