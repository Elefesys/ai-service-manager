"""The import helper must reject source drift before copying any document."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_architecture.py"


@pytest.fixture
def import_project(tmp_path):
    root = tmp_path / "project"
    destination = root / "docs" / "architecture"
    source = tmp_path / "originals"
    destination.mkdir(parents=True)
    source.mkdir()
    (root / "scripts").mkdir()
    shutil.copyfile(SCRIPT, root / "scripts" / SCRIPT.name)
    documents = {"01.md": "Канон A\n".encode(), "02.md": b"Canonical B\n"}
    for name, data in documents.items():
        (source / name).write_bytes(data)
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in documents.items()}
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, source, destination, documents


def run_import(root, source):
    return subprocess.run(
        [sys.executable, str(root / "scripts" / SCRIPT.name), str(source)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_import_is_byte_preserving_and_idempotent(import_project):
    root, source, destination, documents = import_project
    for _ in range(2):
        result = run_import(root, source)
        assert result.returncode == 0, result.stderr
        assert {name: (destination / name).read_bytes() for name in documents} == documents


@pytest.mark.parametrize("failure", ["missing", "source_drift", "target_conflict"])
def test_import_preflights_all_documents_before_writes(import_project, failure):
    root, source, destination, _ = import_project
    if failure == "missing":
        (source / "02.md").unlink()
    elif failure == "source_drift":
        (source / "02.md").write_bytes(b"Unapproved source\n")
    else:
        (destination / "02.md").write_bytes(b"Different existing version\n")
    before = {path.name: path.read_bytes() for path in destination.iterdir()}
    result = run_import(root, source)
    assert result.returncode != 0
    assert {path.name: path.read_bytes() for path in destination.iterdir()} == before


def test_in_place_verification_detects_drift(import_project):
    root, source, destination, _ = import_project
    assert run_import(root, source).returncode == 0
    assert run_import(root, destination).returncode == 0
    (destination / "02.md").write_bytes(b"Changed after import\n")
    result = run_import(root, destination)
    assert result.returncode != 0
    assert "Missing or mismatched canonical source: 02.md" in result.stderr
