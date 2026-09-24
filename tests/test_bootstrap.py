# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""bootstrap.py 环境与依赖检查函数的单元测试。"""

from __future__ import annotations

import json
import subprocess as real_subprocess

import bootstrap


class FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


class StubSubprocess:
    """只替换 run()，其余属性（PIPE / STDOUT 等常量）仍取真正的 subprocess 模块。

    直接替换标准库 subprocess 模块的同名函数会波及同进程里所有使用者；
    这里换成只属于本测试的替身对象，monkeypatch 也只挂 bootstrap 的引用。
    """

    def __init__(self, completed: FakeCompleted) -> None:
        self._completed = completed

    def run(self, *args, **kwargs) -> FakeCompleted:
        return self._completed

    def __getattr__(self, name: str):
        return getattr(real_subprocess, name)


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
        monkeypatch.setattr(bootstrap, "subprocess", StubSubprocess(FakeCompleted(payload)))
        ok, report = bootstrap.check_dependencies("py")
        assert ok is True
        assert report["bili_dl"] == "1.0.0"

    def test_missing_component_fails(self, monkeypatch):
        payload = json.dumps(_fake_report(curl_cffi=None))
        monkeypatch.setattr(bootstrap, "subprocess", StubSubprocess(FakeCompleted(payload)))
        ok, report = bootstrap.check_dependencies("py")
        assert ok is False
        assert report["curl_cffi"] is None

    def test_no_tkinter_fails(self, monkeypatch):
        payload = json.dumps(_fake_report(tkinter=False))
        monkeypatch.setattr(bootstrap, "subprocess", StubSubprocess(FakeCompleted(payload)))
        assert bootstrap.check_dependencies("py")[0] is False

    def test_unparseable_output_degrades(self, monkeypatch):
        monkeypatch.setattr(bootstrap, "subprocess", StubSubprocess(FakeCompleted("boom")))
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


class TestPrepareWithKeepsOldEnv:
    """重建失败时不能把用户原有的 .venv 弄丢（删除不进回收站）。"""

    def test_restores_backup_when_rebuild_fails(self, tmp_path, monkeypatch):
        venv = tmp_path / ".venv"
        (venv / "Scripts").mkdir(parents=True)
        (venv / "Scripts" / "python.exe").write_bytes(b"old-env")

        monkeypatch.setattr(bootstrap, "VENV", venv)
        monkeypatch.setattr(bootstrap, "REPORT", tmp_path / "report.txt")  # 别写到项目目录

        def failing_venv_create(command, timeout=300):
            # 模拟「创建 .venv 失败」：真环境已被改名备份。
            assert not venv.exists()
            raise RuntimeError("模拟断网：创建 .venv 失败")

        monkeypatch.setattr(bootstrap, "run_step", failing_venv_create)

        try:
            bootstrap.prepare_with("py")
        except RuntimeError as error:
            assert "创建 .venv 失败" in str(error)
        else:
            raise AssertionError("prepare_with 应当把失败抛出去")

        assert (venv / "Scripts" / "python.exe").is_file()  # 原环境被放回来了
        assert not (tmp_path / ".venv.bak").exists()
