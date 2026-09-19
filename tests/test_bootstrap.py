"""bootstrap.py 环境与依赖检查函数的单元测试。"""

from __future__ import annotations

import json

import bootstrap


class FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


def _fake_report(**overrides) -> dict:
    report = {
        "python": "3.13.11",
        "tkinter": True,
        "yt_dlp": "2026.9.16.232951.dev0",
        "curl_cffi": "0.15.0",
        "customtkinter": "6.0.0",
        "bili_dl": "1.0.0",
    }
    report.update(overrides)
    return report


class TestCheckDependencies:
    def test_all_ok(self, monkeypatch):
        payload = json.dumps(_fake_report())
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: FakeCompleted(payload))
        ok, report = bootstrap.check_dependencies("py")
        assert ok is True
        assert report["bili_dl"] == "1.0.0"

    def test_missing_component_fails(self, monkeypatch):
        payload = json.dumps(_fake_report(curl_cffi=None))
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: FakeCompleted(payload))
        ok, report = bootstrap.check_dependencies("py")
        assert ok is False
        assert report["curl_cffi"] is None

    def test_no_tkinter_fails(self, monkeypatch):
        payload = json.dumps(_fake_report(tkinter=False))
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: FakeCompleted(payload))
        assert bootstrap.check_dependencies("py")[0] is False

    def test_unparseable_output_degrades(self, monkeypatch):
        monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **k: FakeCompleted("boom"))
        ok, report = bootstrap.check_dependencies("py")
        assert ok is False
        assert report == {}


class TestReportEnvironment:
    def test_lists_components_and_writes_report_file(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(bootstrap, "REPORT", tmp_path / "report.txt")
        monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)
        bootstrap.report_environment(_fake_report())

        out = capsys.readouterr().out
        assert "环境与依赖检查结果" in out
        assert "3.13.11" in out
        assert "1.0.0" in out
        assert "ffmpeg" in out and "未检测到" in out
        assert (tmp_path / "report.txt").is_file()

    def test_ffmpeg_present_is_reported(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(bootstrap, "REPORT", tmp_path / "report.txt")
        monkeypatch.setattr(bootstrap.shutil, "which", lambda name: r"C:\tools\ffmpeg.exe")
        bootstrap.report_environment(_fake_report())
        out = capsys.readouterr().out
        assert "已检测到" in out


class TestCompatible:
    def test_rejects_old_python(self):
        ok, reason = bootstrap.compatible(
            {"impl": "CPython", "version": [3, 9, 0], "tk": True, "venv": True}
        )
        assert ok is False
        assert "3.10" in reason

    def test_rejects_missing_tkinter(self):
        ok, reason = bootstrap.compatible(
            {"impl": "CPython", "version": [3, 13, 0], "tk": False, "venv": True}
        )
        assert ok is False
        assert "tkinter" in reason

    def test_accepts_modern_python(self):
        ok, reason = bootstrap.compatible(
            {"impl": "CPython", "version": [3, 13, 11], "tk": True, "venv": True}
        )
        assert ok is True
        assert reason == ""
