import os
import subprocess

from nsptool import verify
from nsptool.verify import Cache, VerifyResult


def make_file(tmp_path, name="game.nsp", content=b"data"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_cache_hit_for_unchanged_verified_file(tmp_path):
    cache = Cache(tmp_path / "verify.json")
    path = make_file(tmp_path)
    cache.store(VerifyResult(path, ok=True, detail="hashes verified"))

    hit = cache.lookup(path)
    assert hit is not None
    assert hit.cached

    # A fresh instance reads the persisted file.
    assert Cache(tmp_path / "verify.json").lookup(path) is not None


def test_cache_miss_when_file_changes(tmp_path):
    cache = Cache(tmp_path / "verify.json")
    path = make_file(tmp_path)
    cache.store(VerifyResult(path, ok=True, detail="hashes verified"))

    path.write_bytes(b"changed content")
    os.utime(path, (0, 0))
    assert cache.lookup(path) is None


def test_cache_never_serves_failures(tmp_path):
    cache = Cache(tmp_path / "verify.json")
    path = make_file(tmp_path)
    cache.store(VerifyResult(path, ok=False, detail="hash mismatch"))
    assert cache.lookup(path) is None


def test_verify_full_maps_exit_codes(tmp_path, monkeypatch):
    path = make_file(tmp_path)

    def fake_run(cmd, capture_output, text):
        assert "-V" in cmd and str(path) in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="[VERIFIED] ok\n", stderr="")

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    result = verify.verify_full(path)
    assert result.ok

    def fake_run_fail(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="hash mismatch for x.nca\n")

    monkeypatch.setattr(verify.subprocess, "run", fake_run_fail)
    result = verify.verify_full(path)
    assert not result.ok
    assert "hash mismatch" in result.detail


def test_verify_full_detects_swallowed_traceback(tmp_path, monkeypatch):
    path = make_file(tmp_path)

    def fake_run(cmd, capture_output, text):
        return subprocess.CompletedProcess(
            cmd, 0, stdout="Traceback (most recent call last):\nboom\n", stderr=""
        )

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    assert not verify.verify_full(path).ok
