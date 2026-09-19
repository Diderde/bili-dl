# SPDX-License-Identifier: GPL-3.0-only
"""项目常量：链接识别、请求伪装、下载与界面选项。"""

from __future__ import annotations

import re

from bili_dl import __version__

APP_TITLE = "B站音视频下载工具"
APP_VERSION = __version__  # 单一来源：src/bili_dl/__init__.py

# 只接受 bilibili.com / b23.tv，避免把任意 URL 交给 yt-dlp。
ALLOWED_HOSTS = ("bilibili.com", "b23.tv")

BV_PATTERN = re.compile(r"(?<![0-9A-Za-z])(BV[0-9A-Za-z]{10})(?![0-9A-Za-z])", re.IGNORECASE)
AV_PATTERN = re.compile(r"(?<![0-9A-Za-z])(av\d+)(?!\d)", re.IGNORECASE)

# B 站曾对旧版/非浏览器 UA 返回 HTTP 412，保持与当前桌面 Chrome 稳定分支接近。
CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

HTTP_HEADERS = {
    "User-Agent": CHROME_USER_AGENT,
    "Referer": "https://www.bilibili.com/",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Mode": "navigate",
}

# 界面显示文本 -> yt-dlp cookiesfrombrowser 浏览器名（空串表示不读取）。
BROWSER_CHOICES = {
    "不读取浏览器 Cookie": "",
    "Google Chrome": "chrome",
    "Microsoft Edge": "edge",
    "Mozilla Firefox": "firefox",
}
DEFAULT_BROWSER = "不读取浏览器 Cookie"

# 界面显示文本 -> format_sort 上限（bv,ba 分离下载时逐流生效）。
QUALITY_CHOICES = {
    "480p（默认，体积小）": ["res:480"],
    "720p 高清": ["res:720"],
    "1080p 全高清": ["res:1080"],
    "最佳可用画质": [],
}
DEFAULT_QUALITY = "480p（默认，体积小）"
FALLBACK_QUALITY_SORT = ["res:480"]

OUTPUT_TEMPLATE = "%(title).150B [%(id)s] [%(format_id)s].%(ext)s"

# 音视频处理方式：分离保存无需 FFmpeg；合并需要系统已安装 FFmpeg。
MODE_SEPARATE = "分离保存（默认，免 FFmpeg）"
MODE_MERGE = "合并为单文件（需已安装 FFmpeg）"
DOWNLOAD_MODES = (MODE_SEPARATE, MODE_MERGE)
DEFAULT_DOWNLOAD_MODE = MODE_SEPARATE

APPEARANCE_CHOICES = ("深色", "浅色", "跟随系统")
DEFAULT_APPEARANCE = "深色"
