"""Import exact approved sources; fail before writing on any mismatch."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
destination = root / "docs" / "architecture"
manifest = json.loads((destination / "SOURCE_MANIFEST.json").read_text())
for name, expected in manifest.items():
    source = args.source / name
    if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"Missing or mismatched canonical source: {name}")
    target = destination / name
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise SystemExit(
            f"Existing source differs; resolve the architectural version explicitly: {name}"
        )
for name in manifest:
    source, target = args.source / name, destination / name
    if source.resolve() != target.resolve():
        shutil.copyfile(source, target)
print(f"Imported {len(manifest)} checksum-verified original documents. Review and commit the diff.")
