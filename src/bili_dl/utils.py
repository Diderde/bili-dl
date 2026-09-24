# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""纯函数工具：链接归一化、体积格式化、媒体类型与错误信息翻译。"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from bili_dl.constants import ALLOWED_HOSTS, AV_PATTERN, BV_PATTERN, FFMPEG_BUTTON_TEXT


def default_save_dir() -> Path:
    """默认保存位置：程序工作目录下的 downloads 子文件夹（相对路径，随程序走）。

    run.bat / bootstrap 启动时把工作目录固定为程序所在文件夹，
    因此双击启动时即「程序文件夹\\downloads」；不写入任何绝对路径。
    """
    return Path.cwd() / "downloads"


FFMPEG_PORTABLE_DIR = Path.cwd() / "ffmpeg"


def ffmpeg_bin_path() -> Path | None:
    """定位可用的 ffmpeg.exe：优先程序目录的便携安装，其次系统 PATH。"""
    for candidate in (FFMPEG_PORTABLE_DIR / "bin" / "ffmpeg.exe", FFMPEG_PORTABLE_DIR / "ffmpeg.exe"):
        if candidate.is_file():
            return candidate
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def install_ffmpeg_from_zip(zip_path: Path, target_dir: Path = FFMPEG_PORTABLE_DIR) -> Path:
    """从已下载的 FFmpeg zip 中提取 bin 目录到便携位置，返回 bin 目录。

    Gyan.FD 构建的 zip 内部结构为 ffmpeg-x.y.z-essentials_build/bin/ffmpeg.exe，
    此处递归定位 bin 目录后整体复制，随附的 DLL 一并保留。

    target_dir 会被整体替换，因此只允许覆盖「本程序安装的」便携目录：
    若该目录已存在却不像便携安装（例如用户自己的 ffmpeg 构建目录），直接拒绝，
    避免把无关内容删掉（删除不进回收站）。
    """
    with zipfile.ZipFile(zip_path) as archive:
        bin_dirs = {
            name.rsplit("/", 1)[0] for name in archive.namelist()
            if name.endswith("/ffmpeg.exe") or name.endswith("ffmpeg.exe")
        }
        if not bin_dirs:
            raise ValueError("zip 中未找到 ffmpeg.exe，下载内容可能不完整。")
        src_bin = min(bin_dirs)  # 唯一的 bin 目录；有多个时取字典序第一个
        with tempfile.TemporaryDirectory() as tmp:
            # 防 zip-slip：拒绝任何以 .. 或盘符开头的绝对路径条目。
            for name in archive.namelist():
                candidate = (Path(tmp) / name).resolve()
                if not candidate.is_relative_to(Path(tmp).resolve()):
                    raise ValueError(f"zip 条目路径异常，已中止解压：{name}")
            archive.extractall(tmp)
            extracted = Path(tmp) / src_bin
            # 只整体替换「本程序安装的」便携目录：目标已存在却不像便携安装时
            # 拒绝 rmtree（删除不进回收站，那儿可能是用户自己的 ffmpeg 目录）。
            if target_dir.exists() and not (target_dir / "bin" / "ffmpeg.exe").is_file():
                raise ValueError(
                    "目标目录已存在且不是本程序安装的便携 FFmpeg，为避免误删已中止安装：\n"
                    f"{target_dir}\n\n"
                    "请先手动删除或改名该目录，再重新点击「一键下载 FFmpeg」。"
                )
            shutil.rmtree(target_dir, ignore_errors=True)
            shutil.copytree(extracted, target_dir / "bin")
    if not (target_dir / "bin" / "ffmpeg.exe").is_file():
        raise ValueError("FFmpeg 安装失败：bin/ffmpeg.exe 未就位。")
    return target_dir / "bin"


def normalize_source(raw_source: str) -> str:
    """把 BV/av 号或受支持的 B 站链接转换为标准视频页 URL。"""
    value = raw_source.strip()
    if not value:
        raise ValueError("请输入 BV 号或 B 站视频链接。")

    if re.match(r"^https?://", value, re.IGNORECASE):
        parsed = urlparse(value)
        hostname = (parsed.hostname or "").lower()
        if not any(hostname == host or hostname.endswith(f".{host}") for host in ALLOWED_HOSTS):
            raise ValueError("当前仅支持 bilibili.com 或 b23.tv 链接。")
        return value

    if bv_match := BV_PATTERN.search(value):
        return "https://www.bilibili.com/video/" + "BV" + bv_match.group(1)[2:]

    if av_match := AV_PATTERN.search(value):
        return "https://www.bilibili.com/video/av" + av_match.group(1)[2:]

    raise ValueError("未识别到有效的 BV 号、av 号或 B 站链接。")


def human_bytes(value: float) -> str:
    """把字节数格式化为人类可读文本（KiB/MiB/GiB）。"""
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or unit == "GiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GiB"


def detect_media_kind(info: dict) -> str:
    """根据编码信息判断当前下载的是视频流、音频流还是混合媒体。"""
    vcodec = info.get("vcodec")
    acodec = info.get("acodec")
    if vcodec and vcodec != "none" and (not acodec or acodec == "none"):
        return "视频流"
    if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
        return "音频流"
    return "媒体文件"


def clean_error_message(message: str) -> str:
    """把 yt-dlp 的原始报错翻译成用户可操作的中文提示。"""
    text = message.strip()
    for prefix in ("ERROR: ", "ERROR:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    lowered = text.lower()
    if (
        "timed out" in lowered
        or "timeout" in lowered
        or "connection reset" in lowered
        or "giving up after" in lowered
    ):
        return (
            "下载时网络节点超时（多为 B 站 PCDN 分发节点抖动，属偶发）。\n\n"
            "1. 直接重试即可，多数情况第二次就能成功；\n"
            "2. 持续失败时切换网络（如 Wi-Fi ↔ 有线）或关闭代理/加速器后重试；\n"
            "3. 也可稍等几分钟再试，让 B 站重新分配下载节点。\n\n"
            f"原始错误：{text}"
        )

    if "ffmpeg" in lowered and ("not installed" in lowered or "not found" in lowered):
        return (
            "合并模式需要 FFmpeg，但系统未检测到它。\n\n"
            f"1. 关闭本提示，点击界面中的「{FFMPEG_BUTTON_TEXT}」按钮；\n"
            "2. 或复制界面上的 winget 命令安装：winget install Gyan.FFmpeg；\n"
            "3. 装好后点「重新检测」；\n"
            "4. 或改用「分离保存」模式（默认，无需 FFmpeg）。\n\n"
            f"原始错误：{text}"
        )

    if "no video formats found" in lowered:
        return (
            "B站没有返回可下载的格式。通常是 B 站改版导致解析器暂时跟不上。\n\n"
            "1. 重新运行 run.bat，启动器会自动把 yt-dlp 更新到 nightly 版；\n"
            "2. 若仍失败，在“登录状态来源”中选择已登录的浏览器（或 cookies.txt）再试；\n"
            "3. 该视频可能是大会员/地区限制内容，需要对应登录状态；\n"
            "4. 稍后再试，等待 yt-dlp 上游修复。\n\n"
            f"原始错误：{text}"
        )

    if "http error 412" in lowered or "precondition failed" in lowered:
        return (
            "B站返回 HTTP 412（反爬校验拒绝请求）。\n\n"
            "请先在 Chrome、Edge 或 Firefox 中登录 B 站并打开该视频，确认浏览器可以播放；"
            "然后回到软件，在“登录状态来源”中选择同一个浏览器再下载。\n\n"
            "若已经选择浏览器仍报 412：\n"
            "1. 清除旧 cookies.txt，不要同时使用两种 Cookie 来源；\n"
            "2. 关闭浏览器的无痕窗口，并确认软件与浏览器使用同一网络；\n"
            "3. 重新运行 run.bat，确保 yt-dlp 与 curl_cffi 已更新；\n"
            "4. 避免短时间内连续重复下载同一视频。"
        )

    if "could not copy chrome cookie database" in lowered or "cookie database" in lowered:
        return (
            "无法读取浏览器 Cookie 数据库。请完全退出所选浏览器后重试，"
            "或者导出 Netscape 格式的 cookies.txt 并在软件中选择该文件。\n\n"
            f"原始错误：{text}"
        )

    if "impersonate target" in lowered and "not available" in lowered:
        return (
            "浏览器模拟组件不可用。请在项目目录重新运行 run.bat，或执行：\n\n"
            'python -m pip install -U "yt-dlp[default,curl-cffi]"\n\n'
            f"原始错误：{text}"
        )

    return text or "下载失败，未获得详细错误信息。"
