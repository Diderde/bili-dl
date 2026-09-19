"""GUI 层单元测试：以桩替换弹窗与网络，驱动真实窗口验证交互逻辑。"""

from __future__ import annotations

import threading

import customtkinter as ctk
import pytest

from bili_dl import gui as g
from bili_dl import utils as u

MODE_SEPARATE = "分离保存（默认，免 FFmpeg）"
MODE_MERGE = "合并为单文件（需已安装 FFmpeg）"


class _SilentBox:
    """捕获弹窗调用，避免测试中弹出真实对话框。"""

    calls: list[tuple[str, str]] = []

    @classmethod
    def showwarning(cls, title, message): cls.calls.append(("warning", message))

    @classmethod
    def showerror(cls, title, message): cls.calls.append(("error", message))

    @classmethod
    def showinfo(cls, title, message): cls.calls.append(("info", message))


@pytest.fixture(scope="module")
def app():
    """模块级共享一个窗口：同进程反复创建/销毁 CTk 根窗口会导致 tk.tcl 定位失败。"""
    ctk.set_default_color_theme("blue")
    g.messagebox = _SilentBox
    _SilentBox.calls = []
    instance = g.BiliDlApp()
    instance.withdraw()
    yield instance
    instance.destroy()


@pytest.fixture()
def no_ffmpeg(tmp_path, monkeypatch):
    """隔离便携目录并令 PATH 探测失败：等效于系统无 FFmpeg。"""
    monkeypatch.setattr(u, "FFMPEG_PORTABLE_DIR", tmp_path / "absent")
    monkeypatch.setattr(u.shutil, "which", lambda name: None)


class TestFfmpegHint:
    def test_separate_mode_says_no_need(self, app):
        app.mode_menu.set(MODE_SEPARATE)
        app._on_mode_change(app.mode_menu.get())
        assert "无需 FFmpeg" in app.ffmpeg_hint.cget("text")

    def test_merge_without_ffmpeg_warns(self, app, no_ffmpeg):
        app.mode_menu.set(MODE_MERGE)
        app._on_mode_change(app.mode_menu.get())
        assert "未检测到" in app.ffmpeg_hint.cget("text")
        assert app.ffmpeg_dl_btn.cget("state") == "normal"

    def test_recheck_after_install(self, app, tmp_path, monkeypatch):
        portable = tmp_path / "portable"
        (portable / "bin").mkdir(parents=True)
        (portable / "bin" / "ffmpeg.exe").write_bytes(b"fake")
        monkeypatch.setattr(u, "FFMPEG_PORTABLE_DIR", portable)
        app._on_ffmpeg_recheck()
        assert "已检测到" in app.ffmpeg_hint.cget("text")

    def test_copy_winget_command(self, app):
        app._copy_winget_command()
        assert g.WINGET_FFMPEG_COMMAND in app.clipboard_get()
        assert g.WINGET_FFMPEG_COMMAND in app.status_var.get()


class TestSettingsPersistence:
    def test_failed_precheck_still_saves_settings(self, app, no_ffmpeg, tmp_path, monkeypatch):
        """FFmpeg 缺失等预检失败时，用户当前选择也应被保存。"""
        saved: list[dict] = []
        monkeypatch.setattr(g, "save_settings", lambda s: saved.append(s) or True)
        app.url_var.set("BV1vdeJ6KEkR")
        app.mode_menu.set(MODE_MERGE)

        app._start_download()

        assert _SilentBox.calls and _SilentBox.calls[-1][0] == "warning"
        assert saved, "预检失败也应保存设置"
        assert saved[-1]["download_mode"] == MODE_MERGE
        assert "save_dir" not in saved[-1]


class TestDownloadFfmpegButton:
    """在真实 mainloop 中以 after 链驱动：跨线程 after 只有在事件循环运行时才可用。"""

    def test_click_runs_job_and_reenables_on_completion(self, app, tmp_path, monkeypatch):
        failures: list[str] = []
        job_ran = threading.Event()

        # 不借宿主环境的 FFmpeg：显式构造便携安装，保证任意 runner 上前提一致。
        portable = tmp_path / "portable"
        (portable / "bin").mkdir(parents=True)
        (portable / "bin" / "ffmpeg.exe").write_bytes(b"fake")
        monkeypatch.setattr(u, "FFMPEG_PORTABLE_DIR", portable)

        def fake_job():
            job_ran.set()
            app._marshal(app._on_ffmpeg_installed, r"C:\fake\bin")

        monkeypatch.setattr(app, "_ffmpeg_job", fake_job)

        def poll():
            if app._ffmpeg_job_running:
                app.after(50, poll)
                return
            if "normal" not in str(app.ffmpeg_dl_btn.cget("state")):
                failures.append("完成后按钮未恢复")
            if "已检测到" not in app.ffmpeg_hint.cget("text"):
                failures.append("完成后未自动重检测")
            app.quit()

        def driver():
            app._download_ffmpeg_clicked()
            if not app._ffmpeg_job_running:
                failures.append("点击后未进入运行状态")
                app.quit()
                return
            app.after(50, poll)

        def watchdog():
            failures.append("超时")
            app.quit()

        app.after(50, driver)
        app.after(20000, watchdog)
        app.mainloop()
        assert job_ran.is_set()
        assert not failures, failures

    def test_reentry_guard_while_running(self, app, monkeypatch):
        failures: list[str] = []
        started = threading.Event()
        release = threading.Event()

        def fake_job():
            started.set()
            release.wait(5)
            app._marshal(app._on_ffmpeg_installed, r"C:\fake\bin")

        monkeypatch.setattr(app, "_ffmpeg_job", fake_job)

        def second_click():
            if not app._ffmpeg_job_running:
                failures.append("守卫失效：作业未被标记为运行中")
            app._download_ffmpeg_clicked()  # 作业中再次点击应被守卫拦截
            release.set()

        def driver():
            app._download_ffmpeg_clicked()

            def poll_started():
                if started.is_set():
                    second_click()

                    def poll_done():
                        if app._ffmpeg_job_running:
                            app.after(50, poll_done)
                        else:
                            if "normal" not in str(app.ffmpeg_dl_btn.cget("state")):
                                failures.append("完成后按钮未恢复")
                            app.quit()

                    app.after(50, poll_done)
                else:
                    app.after(50, poll_started)

            app.after(50, poll_started)

        def watchdog():
            failures.append("超时")
            app.quit()

        app.after(50, driver)
        app.after(25000, watchdog)
        app.mainloop()
        assert not failures, failures
