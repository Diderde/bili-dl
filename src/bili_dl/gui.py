"""基于 CustomTkinter 的现代化图形界面。"""

from __future__ import annotations

import contextlib
import os
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import TclError, filedialog, messagebox

import customtkinter as ctk

from bili_dl import core
from bili_dl.constants import (
    APP_TITLE,
    APP_VERSION,
    APPEARANCE_CHOICES,
    BROWSER_CHOICES,
    DEFAULT_APPEARANCE,
    DEFAULT_BROWSER,
    DEFAULT_DOWNLOAD_MODE,
    DEFAULT_QUALITY,
    DOWNLOAD_MODES,
    MODE_MERGE,
    QUALITY_CHOICES,
)
from bili_dl.core import (
    HAS_YT_DLP,
    DownloadCancelledByUser,
    DownloadEngine,
    DownloadRequest,
)
from bili_dl.settings import load_settings, save_settings
from bili_dl.utils import (
    FFMPEG_PORTABLE_DIR,
    clean_error_message,
    default_save_dir,
    ffmpeg_bin_path,
    install_ffmpeg_from_zip,
    normalize_source,
)

APPEARANCE_MAP = {"深色": "dark", "浅色": "light", "跟随系统": "system"}

_LOG_PREFIX = {"info": "[info] ", "warning": "[警告] ", "error": "[错误] "}

FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"
WINGET_FFMPEG_COMMAND = "winget install Gyan.FFmpeg"
# Gyan.FD 官方 Essentials 构建（ffmpeg.org 指向的 Windows 官方发布源），版本固定、约 106MB。
FFMPEG_RELEASE_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/"
    "9.0.1/ffmpeg-9.0.1-essentials_build.zip"
)


def ffmpeg_curl_command(zip_path: Path, with_revoke_flag: bool = True) -> list[str]:
    """构造 FFmpeg 下载命令。

    注意不能用 -s/--silent：它会同时关闭进度输出，导致界面拿不到进度；
    --progress-bar 依赖 stderr 的进度行，必须与 -s 互斥。

    --ssl-no-revoke 仅被 Schannel 版 curl（Windows 自带）识别：GitHub 经
    Watt 等加速器中间人代理后吊销检查必然失败，需要跳过；OpenSSL 版
    （如 Git 自带）不认识该选项，由调用方在首次失败后用降级参数重试。
    """
    command = ["curl", "-fL", "--progress-bar", "--retry", "3", "--connect-timeout", "20"]
    if with_revoke_flag:
        command.append("--ssl-no-revoke")
    return command + ["-o", str(zip_path), FFMPEG_RELEASE_URL]


def _format_exception(exc: Exception) -> str:
    if isinstance(exc, core.DownloadError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"


class BiliDlApp(ctk.CTk):
    """主窗口：输入、选项、进度、状态与运行日志。"""

    def __init__(self) -> None:
        super().__init__()
        self._settings = load_settings()
        self._engine: DownloadEngine | None = None
        self._worker: threading.Thread | None = None
        self._ffmpeg_job_running = False

        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("780x720")
        self.minsize(720, 660)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        appearance = self._settings.get("appearance")
        if appearance not in APPEARANCE_CHOICES:
            appearance = DEFAULT_APPEARANCE
        self._appearance = appearance
        ctk.set_appearance_mode(APPEARANCE_MAP.get(appearance, "dark"))

        # 字体统一使用 Windows 自带默认：微软雅黑 UI（中文系统默认 UI 字体）
        # 与 Consolas（系统默认等宽）。显式指定是为了覆盖 customtkinter 的
        # Roboto 默认值（Windows 不自带该字体），并非引入第三方字体。
        self.font_title = ctk.CTkFont(family="Microsoft YaHei UI", size=20, weight="bold")
        self.font_label = ctk.CTkFont(family="Microsoft YaHei UI", size=13)
        self.font_bold = ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold")
        self.font_hint = ctk.CTkFont(family="Microsoft YaHei UI", size=12)
        self.font_mono = ctk.CTkFont(family="Consolas", size=12)

        self.url_var = ctk.StringVar()
        # 保存位置每次启动归零为程序目录下的 downloads 子文件夹，不读取历史设置。
        self.save_var = ctk.StringVar(value=str(default_save_dir()))
        self.cookie_var = ctk.StringVar(value=self._settings.get("cookie_file", ""))
        self.status_var = ctk.StringVar(value="粘贴 BV 号或链接后开始下载。")

        self._build_ui()

        self.bind("<Return>", lambda _event: self._start_download())
        self.bind("<Escape>", lambda _event: self._cancel_download())

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=26, pady=20)
        container.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=APP_TITLE, font=self.font_title, anchor="w").pack(side="left")
        self.appearance_menu = ctk.CTkSegmentedButton(
            header,
            values=list(APPEARANCE_CHOICES),
            command=self._on_appearance_change,
            font=self.font_hint,
            height=28,
        )
        self.appearance_menu.set(self._appearance)
        self.appearance_menu.pack(side="right")

        ctk.CTkLabel(
            container, text="视频 BV 号或链接", font=self.font_label, anchor="w"
        ).pack(fill="x", pady=(18, 4))
        self.url_entry = ctk.CTkEntry(
            container,
            textvariable=self.url_var,
            height=38,
            font=self.font_label,
            placeholder_text="例如：BV1xxxxxxxxxx 或 https://www.bilibili.com/video/...",
        )
        self.url_entry.pack(fill="x")
        self.url_entry.focus_set()
        ctk.CTkLabel(
            container,
            text="支持 BV 号、av 号、bilibili.com 与 b23.tv 链接，可直接粘贴包含链接的整段文字。",
            font=self.font_hint,
            anchor="w",
            text_color="gray60",
        ).pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(container, text="保存位置", font=self.font_label, anchor="w").pack(
            fill="x", pady=(16, 4)
        )
        path_row = ctk.CTkFrame(container, fg_color="transparent")
        path_row.pack(fill="x")
        path_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            path_row, textvariable=self.save_var, height=36, font=self.font_hint
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            path_row, text="浏览", width=72, height=36, font=self.font_hint, command=self._browse_dir
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            path_row,
            text="打开",
            width=72,
            height=36,
            font=self.font_hint,
            fg_color="gray30",
            hover_color="gray45",
            command=self._open_dir,
        ).grid(row=0, column=2, padx=(8, 0))

        options_row = ctk.CTkFrame(container, fg_color="transparent")
        options_row.pack(fill="x", pady=(16, 0))
        options_row.grid_columnconfigure((0, 1), weight=1, uniform="opts")
        left = ctk.CTkFrame(options_row, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        right = ctk.CTkFrame(options_row, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(9, 0))

        ctk.CTkLabel(
            left, text="画质上限（视频流单独选取）", font=self.font_label, anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self.quality_menu = ctk.CTkOptionMenu(
            left,
            values=list(QUALITY_CHOICES),
            height=36,
            font=self.font_hint,
            dynamic_resizing=False,
        )
        quality = self._settings.get("quality")
        self.quality_menu.set(quality if quality in QUALITY_CHOICES else DEFAULT_QUALITY)
        self.quality_menu.pack(fill="x")

        ctk.CTkLabel(
            right, text="登录状态来源（遇 412 时选已登录的浏览器）", font=self.font_label, anchor="w"
        ).pack(fill="x", pady=(0, 4))
        self.browser_menu = ctk.CTkOptionMenu(
            right,
            values=list(BROWSER_CHOICES),
            height=36,
            font=self.font_hint,
            dynamic_resizing=False,
        )
        browser = self._settings.get("browser")
        self.browser_menu.set(browser if browser in BROWSER_CHOICES else DEFAULT_BROWSER)
        self.browser_menu.pack(fill="x")

        ctk.CTkLabel(
            container, text="音视频处理", font=self.font_label, anchor="w"
        ).pack(fill="x", pady=(16, 4))
        self.mode_menu = ctk.CTkOptionMenu(
            container,
            values=list(DOWNLOAD_MODES),
            height=36,
            font=self.font_hint,
            dynamic_resizing=False,
            command=self._on_mode_change,
        )
        mode = self._settings.get("download_mode")
        self.mode_menu.set(mode if mode in DOWNLOAD_MODES else DEFAULT_DOWNLOAD_MODE)
        self.mode_menu.pack(fill="x")

        ffmpeg_row = ctk.CTkFrame(container, fg_color="transparent")
        ffmpeg_row.pack(fill="x", pady=(3, 0))
        self.ffmpeg_hint = ctk.CTkLabel(
            ffmpeg_row, text="", font=self.font_hint, text_color="gray50", anchor="w"
        )
        self.ffmpeg_hint.pack(side="left")
        self.ffmpeg_dl_btn = ctk.CTkButton(
            ffmpeg_row,
            text="一键下载 FFmpeg",
            width=130,
            height=26,
            font=self.font_hint,
            command=self._download_ffmpeg_clicked,
        )
        self.ffmpeg_dl_btn.pack(side="left", padx=(14, 0))
        for text, handler, padx in (
            ("官网下载页", lambda: self._open_url(FFMPEG_DOWNLOAD_URL), (14, 0)),
            ("复制 winget 命令", self._copy_winget_command, (14, 0)),
            ("重新检测", self._on_ffmpeg_recheck, (14, 0)),
        ):
            link = ctk.CTkLabel(
                ffmpeg_row, text=text, font=self.font_hint, text_color="#4a9eff", cursor="hand2"
            )
            link.pack(side="left", padx=padx)
            link.bind("<Button-1>", lambda _event, handler=handler: handler())

        ctk.CTkLabel(
            container, text="或选择 cookies.txt（与浏览器 Cookie 二选一）", font=self.font_label, anchor="w"
        ).pack(fill="x", pady=(16, 4))
        cookie_row = ctk.CTkFrame(container, fg_color="transparent")
        cookie_row.pack(fill="x")
        cookie_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            cookie_row, textvariable=self.cookie_var, height=36, font=self.font_hint, state="readonly"
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            cookie_row, text="选择", width=72, height=36, font=self.font_hint, command=self._choose_cookie
        ).grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            cookie_row,
            text="清除",
            width=72,
            height=36,
            font=self.font_hint,
            fg_color="gray30",
            hover_color="gray45",
            command=lambda: self.cookie_var.set(""),
        ).grid(row=0, column=2, padx=(8, 0))

        ctk.CTkLabel(
            container,
            text="已启用现代 Chrome 请求头与请求节流；遇到 HTTP 412 或解析失败时，请选择已登录的浏览器重试。",
            font=self.font_hint,
            anchor="w",
            text_color="gray60",
        ).pack(fill="x", pady=(12, 0))

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", pady=(18, 0))
        self.start_btn = ctk.CTkButton(
            actions,
            text="开始下载（视频流 + 音频流）",
            height=42,
            font=self.font_bold,
            command=self._start_download,
        )
        self.start_btn.pack(side="left", fill="x", expand=True)
        self.cancel_btn = ctk.CTkButton(
            actions,
            text="取消",
            width=96,
            height=42,
            font=self.font_label,
            fg_color="#a33b3b",
            hover_color="#7f2d2d",
            state="disabled",
            command=self._cancel_download,
        )
        self.cancel_btn.pack(side="left", padx=(10, 0))

        progress_row = ctk.CTkFrame(container, fg_color="transparent")
        progress_row.pack(fill="x", pady=(18, 0))
        progress_row.grid_columnconfigure(0, weight=1)
        self.progress_bar = ctk.CTkProgressBar(progress_row, height=10)
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.percent_label = ctk.CTkLabel(progress_row, text="0.0%", width=64, font=self.font_mono)
        self.percent_label.grid(row=0, column=1, padx=(10, 0))

        ctk.CTkLabel(
            container, textvariable=self.status_var, font=self.font_label, anchor="w", wraplength=700,
            justify="left",
        ).pack(fill="x", pady=(10, 0))

        ctk.CTkLabel(container, text="运行日志", font=self.font_label, anchor="w").pack(
            fill="x", pady=(16, 4)
        )
        self.log_box = ctk.CTkTextbox(
            container, height=120, font=self.font_mono, wrap="word", state="disabled"
        )
        self.log_box.pack(fill="both", expand=True)

        self._refresh_ffmpeg_hint()

    # -------------------------------------------------------------- UI 事件

    def _on_mode_change(self, _value: str) -> None:
        self._refresh_ffmpeg_hint()

    def _on_ffmpeg_recheck(self) -> None:
        self._refresh_ffmpeg_hint()
        self._append_log("info", self.ffmpeg_hint.cget("text"))

    def _refresh_ffmpeg_hint(self) -> None:
        """按当前模式与系统状态更新 FFmpeg 提示与链接区。"""
        if self.mode_menu.get() != MODE_MERGE:
            self.ffmpeg_hint.configure(text="当前为分离保存模式，无需 FFmpeg。", text_color="gray50")
        elif ffmpeg_bin_path():
            self.ffmpeg_hint.configure(text="已检测到 FFmpeg，可直接合并。", text_color="gray50")
        else:
            self.ffmpeg_hint.configure(
                text="未检测到 FFmpeg，可一键下载便携版（装在程序目录）。", text_color="#d98f3f"
            )

    def _open_url(self, url: str) -> None:
        """用系统默认浏览器打开 URL（webbrowser.open 失败时静默，不打断使用）。"""
        with contextlib.suppress(Exception):
            webbrowser.open(url)

    def _download_ffmpeg_clicked(self) -> None:
        """一键下载便携版 FFmpeg：后台线程执行，进度写入运行日志。"""
        if self._ffmpeg_job_running:
            return
        self._ffmpeg_job_running = True
        self.ffmpeg_dl_btn.configure(state="disabled")
        self.status_var.set("正在下载 FFmpeg（约 106MB，视网速需 1~5 分钟）……")
        self._append_log("info", f"开始下载 FFmpeg：{FFMPEG_RELEASE_URL}")
        threading.Thread(target=self._ffmpeg_job, daemon=True, name="ffmpeg-setup").start()

    def _ffmpeg_job(self) -> None:
        import re
        import subprocess
        import tempfile

        def run_curl(zip_path: Path, with_revoke_flag: bool) -> tuple[int, str]:
            """执行下载并边读边上报进度；返回 (退出码, stderr 尾部)。"""
            process = subprocess.Popen(
                ffmpeg_curl_command(zip_path, with_revoke_flag),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
            last_percent = 0
            buffer = ""
            stderr_tail: list[str] = []
            assert process.stderr is not None
            for chunk in iter(lambda: process.stderr.read(32), ""):
                buffer += chunk.replace("\r", "\n")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    stderr_tail = (stderr_tail + [line])[-3:]
                    if match := re.search(r"(\d+(?:\.\d+)?)%", line):
                        percent = int(float(match.group(1)))
                        if percent >= last_percent + 10:
                            last_percent = percent
                            self._marshal(self._on_ffmpeg_progress, percent)
            return process.wait(), "\n".join(stderr_tail)

        try:
            with tempfile.TemporaryDirectory(suffix="_ffdl") as tmp:
                zip_path = Path(tmp) / "ffmpeg.zip"
                self._marshal(self.status_var.set, "正在下载 FFmpeg（约 106MB，视网速需 1~5 分钟）……")
                return_code, stderr_tail = run_curl(zip_path, with_revoke_flag=True)
                if return_code != 0 and "unknown option" in stderr_tail.lower():
                    # OpenSSL 版 curl 不认识 --ssl-no-revoke，降级重试。
                    self._append_log("info", "当前 curl 不支持 --ssl-no-revoke，改用标准参数重试……")
                    return_code, stderr_tail = run_curl(zip_path, with_revoke_flag=False)
                if return_code != 0 or not zip_path.is_file():
                    self._append_log("error", f"curl 退出码 {return_code}：{stderr_tail}")
                    raise RuntimeError(
                        "FFmpeg 下载失败（网络或加速器原因），可改用官网下载页或 winget 命令。"
                    )
                self._marshal(self.status_var.set, "下载完成，正在解压安装……")
                bin_dir = install_ffmpeg_from_zip(zip_path, FFMPEG_PORTABLE_DIR)
            self._marshal(self._on_ffmpeg_installed, str(bin_dir))
        except Exception as exc:  # noqa: BLE001
            self._marshal(self._on_ffmpeg_failed, f"{type(exc).__name__}: {exc}")

    def _on_ffmpeg_progress(self, percent: int) -> None:
        self.status_var.set(f"正在下载 FFmpeg…… {percent}%")

    def _on_ffmpeg_installed(self, bin_dir: str) -> None:
        self._ffmpeg_job_running = False
        self.ffmpeg_dl_btn.configure(state="normal")
        self._refresh_ffmpeg_hint()
        self.status_var.set(f"FFmpeg 已安装到程序目录：{bin_dir}（便携式，删除 ffmpeg 文件夹即卸载）")
        self._append_log("info", f"FFmpeg 安装完成：{bin_dir}")

    def _on_ffmpeg_failed(self, message: str) -> None:
        self._ffmpeg_job_running = False
        self.ffmpeg_dl_btn.configure(state="normal")
        self._refresh_ffmpeg_hint()
        self.status_var.set("FFmpeg 自动下载失败，可用右侧链接或 winget 命令手动安装。")
        self._append_log("error", f"FFmpeg 安装失败：{message}")

    def _copy_winget_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(WINGET_FFMPEG_COMMAND)
        self.status_var.set(
            f"已复制安装命令：{WINGET_FFMPEG_COMMAND}（在 PowerShell 或 CMD 中执行后，点「重新检测」）"
        )

    def _browse_dir(self) -> None:
        path = filedialog.askdirectory(initialdir=self.save_var.get() or str(Path.home()))
        if path:
            self.save_var.set(path)

    def _open_dir(self) -> None:
        path = self.save_var.get().strip()
        if not path or not Path(path).is_dir():
            messagebox.showinfo("保存文件夹", "该文件夹将在首次下载时自动创建。")
            return
        if hasattr(os, "startfile"):
            os.startfile(path)

    def _choose_cookie(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Netscape 格式的 cookies.txt",
            filetypes=[("Cookies text file", "*.txt"), ("All files", "*.*")],
        )
        if path:
            self.cookie_var.set(path)

    def _on_appearance_change(self, value: str) -> None:
        ctk.set_appearance_mode(APPEARANCE_MAP.get(value, "dark"))
        self._appearance = value
        save_settings(self._collect_settings())

    # ------------------------------------------------------------ 下载流程

    def _collect_request(self) -> DownloadRequest:
        url = normalize_source(self.url_var.get())
        save_dir = Path(self.save_var.get()).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)
        if not save_dir.is_dir():
            raise ValueError("保存位置不是有效文件夹。")
        if not os.access(save_dir, os.W_OK):
            raise PermissionError("当前用户没有该文件夹的写入权限。")

        cookie_file = self.cookie_var.get().strip()
        if cookie_file and not Path(cookie_file).is_file():
            raise FileNotFoundError("所选 cookies.txt 不存在。")

        browser_key = BROWSER_CHOICES.get(self.browser_menu.get(), "")
        if cookie_file and browser_key:
            raise ValueError("cookies.txt 与浏览器 Cookie 只能选择一种，请清除其中一项。")

        merge = self.mode_menu.get() == MODE_MERGE
        if merge and ffmpeg_bin_path() is None:
            raise ValueError(
                "合并模式需要 FFmpeg，但未在系统中检测到它。\n\n"
                "点击界面中的「一键下载 FFmpeg」即可自动安装便携版（装在程序目录）；\n"
                "也可以「复制 winget 命令」安装，或改用「分离保存」模式（无需 FFmpeg）。"
            )

        return DownloadRequest(
            url=url,
            save_dir=save_dir,
            quality_label=self.quality_menu.get(),
            cookie_file=cookie_file,
            browser_key=browser_key,
            merge=merge,
        )

    def _collect_settings(self) -> dict[str, str]:
        return {
            "quality": self.quality_menu.get(),
            "browser": self.browser_menu.get(),
            "cookie_file": self.cookie_var.get().strip(),
            "download_mode": self.mode_menu.get(),
            "appearance": self._appearance,
        }

    def _start_download(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        if not HAS_YT_DLP:
            messagebox.showerror(
                "缺少依赖",
                "未安装完整依赖。请在项目目录运行 run.bat，或执行：\n\npython -m pip install -e .",
            )
            return

        try:
            request = self._collect_request()
        except (ValueError, PermissionError, FileNotFoundError, OSError) as exc:
            # 校验失败也保存当前选择（模式/画质/Cookie/主题），与正常路径一致。
            save_settings(self._collect_settings())
            messagebox.showwarning("无法开始下载", str(exc))
            return

        save_settings(
            {
                "quality": request.quality_label,
                "browser": self.browser_menu.get(),
                "cookie_file": request.cookie_file,
                "download_mode": self.mode_menu.get(),
                "appearance": self._appearance,
            }
        )

        self._engine = DownloadEngine(
            request,
            on_progress=lambda percent, text: self._marshal(self._on_engine_progress, percent, text),
            on_status=lambda text: self._marshal(self.status_var.set, text),
            on_log=lambda level, msg: self._marshal(self._append_log, level, msg),
        )

        self._set_busy(True)
        self._append_log("info", f"开始下载：{request.url}")
        self.status_var.set("正在以浏览器请求方式解析视频信息……")
        self._worker = threading.Thread(
            target=self._run_engine,
            args=(self._engine,),
            daemon=True,
            name="bili-dl-worker",
        )
        self._worker.start()

    def _cancel_download(self) -> None:
        if self._engine is not None and self._worker is not None and self._worker.is_alive():
            self._engine.cancel()
            self.status_var.set("正在取消……")
            self.cancel_btn.configure(state="disabled")

    def _marshal(self, func, *args) -> None:
        """把回调排入主线程执行；窗口已销毁时静默放弃。"""
        with contextlib.suppress(TclError):
            self.after(0, func, *args)

    def _run_engine(self, engine: DownloadEngine) -> None:
        try:
            files = engine.run()
        except DownloadCancelledByUser:
            self._marshal(self._on_cancelled)
        except Exception as exc:  # 兜底保证界面一定恢复可用。
            traceback.print_exc()
            self._marshal(self._on_failed, clean_error_message(_format_exception(exc)))
        else:
            self._marshal(self._on_success, str(engine.request.save_dir), files)

    # ---------------------------------------------------------- 状态回调

    def _on_engine_progress(self, percent: float, text: str) -> None:
        self.progress_bar.set(percent / 100.0)
        self.percent_label.configure(text=f"{percent:.1f}%")
        self.status_var.set(text)

    def _set_busy(self, busy: bool) -> None:
        self.start_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        if not busy:
            self._engine = None

    def _on_success(self, save_dir: str, files: list[str]) -> None:
        self._set_busy(False)
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="100%")
        self.status_var.set("下载完成：视频流与音频流已分别保存。")
        self._append_log(
            "info",
            "下载完成：" + ("、".join(Path(f).name for f in files) or "（未取得文件名）"),
        )
        listing = "\n".join(f"· {Path(f).name}" for f in files[:6]) or "（未取得文件名）"
        if len(files) > 6:
            listing += f"\n· ……共 {len(files)} 个文件"
        messagebox.showinfo(
            "下载完成",
            f"已保存 {len(files)} 个文件：\n\n{listing}\n\n保存位置：\n{save_dir}",
        )

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.progress_bar.set(0.0)
        self.percent_label.configure(text="0.0%")
        self.status_var.set("下载失败，详情见弹窗与运行日志。")
        self._append_log("error", message)
        messagebox.showerror("下载失败", message)

    def _on_cancelled(self) -> None:
        self._set_busy(False)
        self.progress_bar.set(0.0)
        self.percent_label.configure(text="0.0%")
        self.status_var.set("已取消下载。")
        self._append_log("info", "用户取消了下载。")

    def _append_log(self, level: str, message: str) -> None:
        prefix = _LOG_PREFIX.get(level, "")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{prefix}{message.strip()}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_close(self) -> None:
        busy = self._worker is not None and self._worker.is_alive()
        if busy:
            if not messagebox.askyesno("正在下载", "下载尚未完成，确定退出吗？"):
                return
            if self._engine is not None:
                self._engine.cancel()
        save_settings(self._collect_settings())
        self.destroy()


def run() -> None:
    """创建主窗口并进入事件循环。"""
    ctk.set_default_color_theme("blue")
    app = BiliDlApp()
    app.mainloop()
