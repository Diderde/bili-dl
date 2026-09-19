"""用户设置持久化：JSON 存于 %APPDATA%/bili_dl，损坏时静默回退默认值。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from bili_dl.constants import (
    DEFAULT_APPEARANCE,
    DEFAULT_BROWSER,
    DEFAULT_DOWNLOAD_MODE,
    DEFAULT_QUALITY,
)

SETTINGS_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "bili_dl"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

DEFAULTS: dict[str, str] = {
    # 注意：保存位置不持久化——每次启动重置为程序目录下的 downloads
    # 子文件夹（见 utils.default_save_dir），设置文件中不记录任何本机路径。
    "quality": DEFAULT_QUALITY,
    "browser": DEFAULT_BROWSER,
    "cookie_file": "",
    "download_mode": DEFAULT_DOWNLOAD_MODE,
    "appearance": DEFAULT_APPEARANCE,
}


def load_settings() -> dict[str, str]:
    """读取设置；缺失或损坏时返回默认值（绝不抛异常影响启动）。"""
    settings = dict(DEFAULTS)
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if not isinstance(stored, dict):
        return settings

    for key, default in DEFAULTS.items():
        value = stored.get(key)
        if isinstance(value, str) and (value or not default):
            settings[key] = value
    return settings


def save_settings(settings: dict[str, str]) -> bool:
    """写入设置；失败时返回 False（持久化失败不应中断程序）。"""
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True
