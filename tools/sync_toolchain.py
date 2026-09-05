"""Derive runtime selector and hashed pip requirements from their canonical locks."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def requirements_body(text):
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    pins = json.loads((ROOT / "build/toolchain.lock.json").read_text())
    actual = subprocess.run(["uv", "--version"], text=True, capture_output=True, check=True).stdout.strip()
    if actual.split()[:2] != ["uv", pins["uv_version"]]:
        raise ValueError("Install the uv version named in build/toolchain.lock.json.")
    subprocess.run(["uv", "lock", "--check"], cwd=ROOT, check=True)
    requirements = subprocess.run(["uv", "export", "--frozen", "--all-groups", "--no-emit-project"], cwd=ROOT, text=True, capture_output=True, check=True).stdout
    derived = {".python-version": pins["python_version"] + "\n", "requirements.lock": requirements}
    if args.check:
        for name, expected in derived.items():
            observed = (ROOT / name).read_text(encoding="utf-8")
            if (requirements_body(observed) != requirements_body(expected)) if name == "requirements.lock" else observed != expected:
                raise ValueError(f"Derived {name} differs from its lock owner. Run tools/sync_toolchain.py.")
        print("PASS: Python selector and hashed requirements match their canonical locks; uv lock is current")
        return
    # Prove regeneration in scratch before replacing either derived file.
    (ROOT / "work").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / "work") as scratch:
        for name, content in derived.items():
            restored = Path(scratch) / name
            restored.write_text(content, encoding="utf-8", newline="\n")
            assert restored.read_text(encoding="utf-8") == content
        for name in derived:
            (ROOT / name).write_bytes((Path(scratch) / name).read_bytes())
    print("PASS: regenerated Python selector and hashed requirements after scratch round-trip proof")


if __name__ == "__main__":
    main()
