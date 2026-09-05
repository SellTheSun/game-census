"""Validate and deterministically export the canonical planning documents.

Standard library only. This does not install or run the proposed application.
"""
import argparse
import hashlib
import io
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOCROOT = ROOT / "docs"
PACKET = ROOT / "docs/build-tasks/initial-release"
PRD = DOCROOT / "PRD-game-census.md"
PRS = DOCROOT / "PRS-game-census.md"
DOCS = [PRD, PRS, DOCROOT / "BACKLOG.md", *[PACKET / name for name in ("implementation_plan.md", "task_checklist.md", "agent_prompt.md")]]
LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def read(path):
    return path.read_text(encoding="utf-8-sig")


def check():
    texts = {path.name: read(path) for path in DOCS}
    ids = set(re.findall(r"^\| ((?:FR|NFR)-\d+) \|", texts[PRD.name], re.M))
    if len(ids) != 14:
        raise ValueError(f"Expected 14 declared requirements; found {len(ids)}")
    for name in (PRS.name, "implementation_plan.md", "task_checklist.md"):
        missing = ids - set(re.findall(r"\b(?:FR|NFR)-\d+\b", texts[name]))
        if missing:
            raise ValueError(f"{name} does not reference requirements: {sorted(missing)}")
    for path, expected in ((PRD, 9), (PRS, 10)):
        numbers = [int(n) for n in re.findall(r"^## (\d+)\. ", texts[path.name], re.M)]
        if numbers != list(range(1, expected + 1)):
            raise ValueError(f"{path.name}: expected {expected} ordered standard sections; found {numbers}")
    for section in re.split(r"^## \d+\. ", texts[PRS.name], flags=re.M)[1:]:
        if not re.search(r"\b(?:FR|NFR)-\d+\b", section):
            raise ValueError("PRS section lacks capability traceability")
    if re.search(r"^\| ((?:FR|NFR)-\d+) \|", read(PACKET / "PRD.md"), re.M):
        raise ValueError("Legacy PRD path must be a pointer, not competing requirements")
    for path in [ROOT / "README.md", *sorted(DOCROOT.rglob("*.md"))]:
        for _, href in LINK.findall(read(path)):
            if re.match(r"^[a-zA-Z][\w+.-]*:", href) or href.startswith("#"):
                continue
            target = (path.parent / href.split("#", 1)[0]).resolve()
            if not target.is_relative_to(ROOT) or not target.is_file():
                raise ValueError(f"Missing/unsafe local link in {path.name}: {href}")
    tasks = re.findall(r"^- \[([ x/])\] ", texts["task_checklist.md"], re.M)
    if not tasks:
        raise ValueError("Implementation checklist has no status markers")
    if tasks.count("/") > 4:
        raise ValueError("More active checklist items than available executing agents")
    if "x" in tasks and not (PACKET / "walkthrough.md").exists():
        raise ValueError("Completed implementation items require an evidence walkthrough")
    tiers = [(100, 300), (400, 1800), (2000, 7200)]
    calls = sum(n * 86400 // interval for n, interval in tiers)
    assert calls == 72000
    print(f"PASS: PRD/PRS have 9/10 ordered sections; {len(ids)} requirement IDs covered in PRS, plan and checklist")
    print("PASS: local file links resolve; legacy PRD is a pointer; canonical ownership is explicit")
    print(f"PASS: {len(tasks)} product tasks; {tasks.count('x')} complete, {tasks.count('/')} active, {tasks.count(' ')} future")
    print("PASS: illustrative player budget = 72000 calls/day; annual observations = 26280000")


def paths_for_export():
    root_files = ["README.md", "LICENSE", ".gitignore", ".dockerignore", ".python-version", "Dockerfile", "compose.yaml", "pyproject.toml", "uv.lock", "requirements.lock"]
    allowed = [*[ROOT / name for name in root_files], *sorted((ROOT / "tools").glob("*.py")), *sorted(DOCROOT.rglob("*"))]
    for folder in ("src", "tests", "build"):
        allowed.extend(path for path in (ROOT / folder).rglob("*") if "__pycache__" not in path.parts and path.suffix != ".pyc")
    return sorted({p for p in allowed if p.is_file()}, key=lambda p: p.relative_to(ROOT).as_posix())


def render_combined():
    paths = [ROOT / "README.md", *DOCS, PACKET / "walkthrough.md", *sorted((PACKET / "evidence").glob("*"))]
    paths = [path for path in paths if path.is_file()]
    anchors = {p.resolve(): f"part-{i}" for i, p in enumerate(paths)}
    parts = ["# Game Census — development plan and implementation evidence\n\nGenerated from the canonical repository documents. The checklist and walkthrough distinguish the first usable slice from the future full-product roadmap.\n"]
    for path in paths:
        body = read(path)
        if path.suffix == ".md":
            def replace(match):
                label, href = match.groups()
                if re.match(r"^[a-zA-Z][\w+.-]*:", href) or href.startswith("#"):
                    return match.group(0)
                target = (path.parent / href.split("#", 1)[0]).resolve()
                if target in anchors:
                    return f"[{label}](#{anchors[target]})"
                return match.group(0)
            body = LINK.sub(replace, body)
        else:
            language = "json" if path.suffix == ".json" else "text"
            body = f"## {path.name}\n\n```{language}\n{body.rstrip()}\n```\n"
        parts.append(f'\n<a id="{anchors[path.resolve()]}"></a>\n\n{body.rstrip()}\n')
    return "\n---\n".join(parts).encode("utf-8")


def render_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in paths_for_export():
            name = "game-census/" + path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 4, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def write_new_or_identical(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite a different artifact: {path}. Use a new output directory.")
    else:
        path.write_bytes(data)
    print(f"SHA256 {path.name}: {hashlib.sha256(data).hexdigest()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only structural checks")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    check()
    if args.check:
        return 0
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Preserve relative links among standalone PRD/PRS and their supporting docs.
    for path in sorted(DOCROOT.rglob("*")):
        if path.is_file():
            target = output / path.relative_to(DOCROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            write_new_or_identical(target, path.read_bytes())
    write_new_or_identical(output / "game-census-development-plan.md", render_combined())
    write_new_or_identical(output / "game-census-repository.zip", render_zip())
    print("PASS: standalone documents, combined Markdown and ZIP exports created or matched existing bytes")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, AssertionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
