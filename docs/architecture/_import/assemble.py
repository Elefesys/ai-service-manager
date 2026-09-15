"""One-time import transport repair, guarded by the pre-existing source manifest."""

import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
staging = root / "_import"
manifest = json.loads((root / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
corrections = json.loads((staging / "corrections.json").read_text(encoding="utf-8"))
baseline = "AI_Service_Manager_Architecture_Baseline_v0.28.md"
names = sorted(name for name in manifest if name != baseline)
if len(names) != 10 or set(corrections) - set(names):
    raise SystemExit("Unexpected canonical document set")
outputs = {}
for name in names:
    if Path(name).name != name:
        raise SystemExit("Invalid source name")
    if name == "01_ARCHITECTURE_SPEC.md":
        data = b"".join((staging / f"spec-{i}.txt").read_bytes() for i in range(1, 5))
    else:
        data = (root / name).read_bytes()
    if name in corrections:
        correction = corrections[name]
        if hashlib.sha256(data).hexdigest() != correction["source_sha256"]:
            raise SystemExit(f"Staged source changed: {name}")
        lines = data.decode("utf-8").splitlines(keepends=True)
        last_end = 0
        for start, end, replacement in correction["edits"]:
            if not (last_end <= start <= end <= len(lines)) or not isinstance(replacement, str):
                raise SystemExit(f"Invalid restoration edit: {name}")
            last_end = end
        for start, end, replacement in reversed(correction["edits"]):
            lines[start:end] = [replacement]
        data = "".join(lines).encode("utf-8")
    if hashlib.sha256(data).hexdigest() != manifest[name]:
        raise SystemExit(f"Restored source does not match approved original: {name}")
    outputs[name] = data
outputs[baseline] = (staging / "baseline-prefix.txt").read_bytes() + outputs[names[0]]
for name in names[1:]:
    outputs[baseline] += f"\n\n---\n\n## Исходный файл: {name}\n\n".encode() + outputs[name]
if hashlib.sha256(outputs[baseline]).hexdigest() != manifest[baseline]:
    raise SystemExit("Combined baseline differs from approved original")
# Validate every document before writing any canonical output.
for name, data in outputs.items():
    (root / name).write_bytes(data)
    print(f"SHA256 VERIFIED {manifest[name]} {name}")
shutil.rmtree(staging)
print("All 11 approved originals restored exactly; temporary import payload removed.")
