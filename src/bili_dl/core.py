# SPDX-License-Identifier: GPL-3.0-only
"""下载核心：组装 yt-dlp 选项并执行下载。

本模块不依赖任何 GUI 库，便于单元测试；GUI 通过回调与引擎通信。
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bili_dl.constants import (
    DEFAULT_QUALITY,
    FALLBACK_QUALITY_SORT,
    HTTP_HEADERS,
    OUTPUT_TEMPLATE,
    QUALITY_CHOICES,
)
from bili_dl.utils import detect_media_kind, ffmpeg_bin_path, human_bytes

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError

    try:
        import curl_cffi  # noqa: F401  # 启用浏览器 TLS 模拟所需。
        from yt_dlp.networking.impersonate import ImpersonateTarget

        IMPERSONATION_AVAILABLE = True
    except (ImportError, AttributeError):
        ImpersonateTarget = None
        IMPERSONATION_AVAILABLE = False

    HAS_YT_DLP = True
except ImportError:  # 保证 GUI 仍能启动并给出安装提示。
    yt_dlp = None
    ImpersonateTarget = None
    IMPERSONATION_AVAILABLE = False
    HAS_YT_DLP = False

    class DownloadError(Exception):
        """yt-dlp 未安装时的占位异常类型。"""


class DownloadCancelledByUser(Exception):
    """用户主动取消下载。"""


ProgressCallback = Callable[[float, str], None]
StatusCallback = Callable[[str], None]
LogCallback = Callable[[str, str], None]
HookCallback = Callable[[dict], None]


@dataclass(frozen=True)
class DownloadRequest:
    """一次下载所需的全部输入。

    impersonate 默认关闭：实测 B 站当前风控下，TLS 指纹模拟会让 playurl
    返回空格式列表（No video formats found）；Chrome 请求头已足够。
    """

    url: str
    save_dir: Path
    quality_label: str = DEFAULT_QUALITY
    cookie_file: str = ""
    browser_key: str = ""
    impersonate: bool = False
    # True 时合并为单个文件（需要系统安装 FFmpeg）；默认分离保存。
    merge: bool = False


class YtdlpLoggerBridge:
    """把 yt-dlp 日志转发到回调：debug 静默，info 记录，warning/error 上浮。"""

    def __init__(self, on_log: LogCallback | None) -> None:
        self._on_log = on_log

    def debug(self, message: str) -> None:
        return

    def info(self, message: str) -> None:
        if self._on_log and message:
            self._on_log("info", str(message))

    def warning(self, message: str) -> None:
        if self._on_log and message:
            self._on_log("warning", str(message))

    def error(self, message: str) -> None:
        if self._on_log and message:
            self._on_log("error", str(message))


def build_ydl_options(
    request: DownloadRequest,
    progress_hook: HookCallback | None = None,
    logger: object | None = None,
    postprocessor_hook: HookCallback | None = None,
) -> dict:
    """构造 yt-dlp 选项。默认 "bv,ba" 分别下载两个流，不写 "+" 即不需要 FFmpeg 合并。"""
    # 合并模式的 "/b" 兜底：无法合并时退回最佳单文件流。
    format_spec = "bv*+ba/b" if request.merge else "bv,ba"

    options: dict = {
        "format": format_spec,
        "format_sort": list(QUALITY_CHOICES.get(request.quality_label, FALLBACK_QUALITY_SORT)),
        "outtmpl": os.path.join(str(request.save_dir), OUTPUT_TEMPLATE),
        "noplaylist": True,
        "ignoreerrors": False,
        "abort_on_error": True,
        "overwrites": False,
        "continuedl": True,
        "retries": 8,
        "fragment_retries": 8,
        "extractor_retries": 3,
        "file_access_retries": 3,
        # 并发过高更容易触发反爬/限流。
        "concurrent_fragment_downloads": 2,
        "sleep_interval_requests": 0.75,
        "socket_timeout": 30,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "http_headers": dict(HTTP_HEADERS),
    }

    if request.merge:
        # B 站主流编码（AVC/AAC）可无损封装进 mp4。
        options["merge_output_format"] = "mp4"
        if postprocessor_hook is not None:
            options["postprocessor_hooks"] = [postprocessor_hook]

    if progress_hook is not None:
        options["progress_hooks"] = [progress_hook]
    if logger is not None:
        options["logger"] = logger
    if request.cookie_file:
        options["cookiefile"] = request.cookie_file
    elif request.browser_key:
        # yt-dlp 参数顺序：browser, profile, keyring, container。
        options["cookiesfrombrowser"] = (request.browser_key, None, None, None)
    if request.impersonate and IMPERSONATION_AVAILABLE and ImpersonateTarget is not None:
        # 仅在 B 站恢复旧式 412 风控时手动开启；平时会让 playurl 取不到格式。
        options["impersonate"] = ImpersonateTarget.from_str("chrome")

    return options


class DownloadEngine:
    """在线程中执行一次下载；cancel() 可安全中止，进度经回调上报。"""

    def __init__(
        self,
        request: DownloadRequest,
        on_progress: ProgressCallback | None = None,
        on_status: StatusCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> None:
        self.request = request
        self._on_progress = on_progress
        self._on_status = on_status
        self._on_log = on_log
        self._cancel_event = threading.Event()
        self._finished_files: list[str] = []
        self._downloaded_files: list[str] = []
        self._completed_streams = 0

    @property
    def files(self) -> list[str]:
        """已保存文件：合并模式优先取后处理上报的最终文件，否则回退下载记录。"""
        return list(self._finished_files or self._downloaded_files)

    def cancel(self) -> None:
        """请求中止：由进度钩子在下一个数据块时抛出取消异常。"""
        self._cancel_event.set()

    def run(self) -> list[str]:
        """阻塞执行下载；成功返回已保存文件路径列表，取消/失败抛异常。"""
        if self.request.merge and ffmpeg_bin_path() is None:
            raise RuntimeError(
                "合并模式需要 FFmpeg，但未在系统中检测到它。\n\n"
                "点击界面中的「一键下载 FFmpeg」即可自动安装便携版（装在程序目录）；\n"
                "也可以「复制 winget 命令」安装，或改用「分离保存」模式（无需 FFmpeg）。"
            )
        if yt_dlp is None:
            raise RuntimeError("未安装 yt-dlp，无法下载。请在项目目录运行 run.bat 重新安装依赖。")
        self._check_cancelled()

        options = build_ydl_options(
            self.request,
            self.progress_hook,
            YtdlpLoggerBridge(self._on_log),
            postprocessor_hook=self._postprocessor_hook,
        )
        if self.request.merge:
            options["ffmpeg_location"] = str(ffmpeg_bin_path().parent)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                result_code = ydl.download([self.request.url])
        except DownloadCancelledByUser:
            raise
        except DownloadError:
            if self._cancel_event.is_set():
                raise DownloadCancelledByUser("用户取消了下载。") from None
            raise
        except Exception as exc:
            if self._cancel_event.is_set():
                raise DownloadCancelledByUser("用户取消了下载。") from exc
            raise

        if result_code != 0:
            raise RuntimeError(f"yt-dlp 返回错误码 {result_code}")
        self._check_cancelled()
        return self.files

    def _postprocessor_hook(self, data: dict) -> None:
        """yt-dlp 后处理事件：合并完成后记录最终输出文件（多个后处理阶段会重复上报，去重）。"""
        self._check_cancelled()
        if data.get("status") == "finished":
            info = data.get("info_dict") or {}
            filename = info.get("filepath") or info.get("filename")
            if filename and filename not in self._finished_files:
                self._finished_files.append(str(filename))

    def progress_hook(self, data: dict) -> None:
        """yt-dlp 进度事件：换算整体进度（两个流各占一半）并上报。"""
        self._check_cancelled()
        status = data.get("status")
        info = data.get("info_dict") or {}
        media_kind = detect_media_kind(info)

        if status == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            stream_percent = (downloaded / total * 100.0) if total else 0.0
            overall = self._overall_percent(stream_percent)

            details = (
                f"正在下载{media_kind}"
                f"（{self._completed_streams + 1}/{self._expected_streams}）：{overall:.1f}%"
            )
            speed = data.get("speed") or 0
            if speed:
                details += f" · {human_bytes(speed)}/s"
            eta = data.get("eta")
            if eta is not None:
                details += f" · 剩余约 {int(eta)} 秒"
            self._emit_progress(overall, details)

        elif status == "finished":
            self._completed_streams += 1
            # 下载记录始终保留：合并模式若因 "/b" 兜底选中单文件格式，
            # 后处理钩子不会触发，此时以下载记录为准。
            if filename := data.get("filename"):
                self._downloaded_files.append(str(filename))
            # 完成事件只按已完成流数推进整体进度，避免中途跳到 100%。
            self._emit_progress(
                self._completed_streams * 100.0 / self._expected_streams,
                f"{media_kind}下载完成，正在处理下一个文件……",
            )

        elif status == "error":
            if self._on_status:
                self._on_status(f"{media_kind}下载出错。")

    @property
    def _expected_streams(self) -> int:
        """B 站音视频始终按 2 个流下载（合并模式多一步后处理），各占一半进度。"""
        return 2

    def _overall_percent(self, stream_percent: float) -> float:
        return (self._completed_streams * 100.0 + stream_percent) / self._expected_streams

    def _check_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise DownloadCancelledByUser("用户取消了下载。")

    def _emit_progress(self, percent: float, text: str) -> None:
        if self._on_progress:
            self._on_progress(max(0.0, min(100.0, percent)), text)
