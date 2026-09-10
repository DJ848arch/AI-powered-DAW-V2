"""Crash-safe ProjectManager save/load tests."""

import json
import os
from datetime import datetime, timedelta

import pytest

from project import ProjectManager

SCHEMA = ProjectManager.SCHEMA_VERSION


def _pm(tmp_path):
    return ProjectManager(projects_dir=str(tmp_path / "projects"))


def test_new_save_load_roundtrip(tmp_path):
    pm = _pm(tmp_path)
    project = pm.new_project("My Song")
    path = str(tmp_path / "mysong.daw")

    assert pm.save_project(path, project) is True

    loaded = pm.load_project(path)
    assert loaded["name"] == "My Song"
    assert loaded["version"] == SCHEMA
    assert "timeline" in loaded
    assert "transport" in loaded
    assert pm.current_project is loaded


def test_overwrite_backup_contains_old_data(tmp_path):
    pm = _pm(tmp_path)
    path = str(tmp_path / "song.daw")

    project_a = pm.new_project("Project A")
    assert pm.save_project(path, project_a) is True

    project_b = pm.new_project("Project B")
    assert pm.save_project(path, project_b) is True

    backup_dir = tmp_path / ".backups"
    backups = list(backup_dir.iterdir())
    assert len(backups) == 1

    with open(backups[0], "r") as f:
        backup_data = json.load(f)
    assert backup_data["name"] == "Project A"
    assert backup_data["version"] == SCHEMA

    loaded = pm.load_project(path)
    assert loaded["name"] == "Project B"


def test_first_save_creates_no_backup(tmp_path):
    pm = _pm(tmp_path)
    path = str(tmp_path / "first.daw")
    project = pm.new_project("First Save")

    assert pm.save_project(path, project) is True
    assert not (tmp_path / ".backups").exists()

    loaded = pm.load_project(path)
    assert loaded["name"] == "First Save"


def test_failed_write_after_backup_preserves_original(tmp_path, monkeypatch):
    pm = _pm(tmp_path)
    path = str(tmp_path / "keep.daw")

    original = pm.new_project("Original")
    assert pm.save_project(path, original) is True

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", boom)

    replacement = pm.new_project("Replacement")
    assert pm.save_project(path, replacement) is False

    # Destination must still be the old good file; tmp must not remain.
    assert not os.path.exists(path + ".tmp")
    loaded = pm.load_project(path)
    assert loaded["name"] == "Original"


def test_atomic_write_fails_when_dest_is_directory(tmp_path):
    """Making dest a directory causes _atomic_write_json to fail; no leftover tmp."""
    pm = _pm(tmp_path)
    dest = tmp_path / "isdir.daw"
    dest.mkdir()
    (dest / "marker").write_text("keep")

    assert pm.save_project(str(dest), pm.new_project("Should Fail")) is False
    assert dest.is_dir()
    assert (dest / "marker").read_text() == "keep"
    assert not os.path.exists(str(dest) + ".tmp")


def test_load_project_raises_valueerror_on_missing_keys(tmp_path):
    pm = _pm(tmp_path)
    path = tmp_path / "invalid.daw"
    path.write_text(json.dumps({"name": "Broken", "version": "1.0"}))

    with pytest.raises(ValueError, match="required"):
        pm.load_project(str(path))


def test_load_project_raises_on_invalid_json(tmp_path):
    pm = _pm(tmp_path)
    path = tmp_path / "truncated.daw"
    path.write_text('{"version": "1.0", "timeline":')

    with pytest.raises(json.JSONDecodeError):
        pm.load_project(str(path))


def test_autosave_writes_valid_json(tmp_path):
    pm = _pm(tmp_path)
    path = str(tmp_path / "session.daw")
    project = pm.new_project("Autosave Me")

    pm.autosave(path, project)

    autosave_path = tmp_path / ".autosave" / "session.daw.autosave"
    assert autosave_path.is_file()
    with open(autosave_path, "r") as f:
        data = json.load(f)
    assert data["name"] == "Autosave Me"
    assert data["version"] == SCHEMA


def test_backup_rotation_keeps_at_most_10(tmp_path, monkeypatch):
    pm = _pm(tmp_path)
    path = str(tmp_path / "rotate.daw")

    # Unique timestamps so each overwrite creates a distinct backup file.
    clock = {"n": 0}
    real_datetime = datetime

    class FakeDateTime:
        @staticmethod
        def now():
            clock["n"] += 1
            return real_datetime(2026, 1, 1, 12, 0, 0) + timedelta(seconds=clock["n"])

    monkeypatch.setattr("project.datetime", FakeDateTime)

    project = pm.new_project("Rotate")
    assert pm.save_project(path, project) is True  # first save: no backup

    for i in range(11):
        project["name"] = f"Overwrite {i}"
        assert pm.save_project(path, project) is True

    backup_dir = tmp_path / ".backups"
    backups = [
        name
        for name in os.listdir(backup_dir)
        if name.startswith(os.path.basename(path))
    ]
    assert len(backups) <= 10
    assert len(backups) == 10
