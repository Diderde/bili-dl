"""设置持久化的单元测试（使用临时目录，不触碰真实 %APPDATA%）。"""

from __future__ import annotations

import json

import pytest

from bili_dl import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """把设置文件重定向到临时目录。"""
    settings_dir = tmp_path / "bili_dl"
    monkeypatch.setattr(settings, "SETTINGS_DIR", settings_dir)
    monkeypatch.setattr(settings, "SETTINGS_FILE", settings_dir / "settings.json")
    return settings_dir


class TestLoadSettings:
    def test_missing_file_returns_defaults(self):
        loaded = settings.load_settings()
        assert loaded == settings.DEFAULTS

    def test_corrupt_json_returns_defaults(self, isolated_settings):
        isolated_settings.mkdir(parents=True)
        (isolated_settings / "settings.json").write_text("{不是JSON", encoding="utf-8")
        assert settings.load_settings() == settings.DEFAULTS

    def test_non_dict_json_returns_defaults(self, isolated_settings):
        isolated_settings.mkdir(parents=True)
        (isolated_settings / "settings.json").write_text('["列表"]', encoding="utf-8")
        assert settings.load_settings() == settings.DEFAULTS

    def test_unknown_keys_are_ignored(self, isolated_settings):
        isolated_settings.mkdir(parents=True)
        (isolated_settings / "settings.json").write_text(
            json.dumps({"quality": "720p 高清", "hacker": "x"}), encoding="utf-8"
        )
        loaded = settings.load_settings()
        assert loaded["quality"] == "720p 高清"
        assert "hacker" not in loaded

    def test_non_string_values_rejected(self, isolated_settings):
        isolated_settings.mkdir(parents=True)
        (isolated_settings / "settings.json").write_text(
            json.dumps({"quality": 123}), encoding="utf-8"
        )
        assert settings.load_settings()["quality"] == settings.DEFAULTS["quality"]

    def test_save_dir_is_not_persisted(self, isolated_settings):
        """旧版设置文件里的 save_dir 应被忽略：不回填、不保留。"""
        isolated_settings.mkdir(parents=True)
        (isolated_settings / "settings.json").write_text(
            json.dumps({"save_dir": r"C:\Users\somewhere\Downloads", "quality": "720p 高清"}),
            encoding="utf-8",
        )
        loaded = settings.load_settings()
        assert "save_dir" not in loaded
        assert loaded["quality"] == "720p 高清"


class TestSaveSettings:
    def test_round_trip(self, isolated_settings):
        payload = dict(settings.DEFAULTS, quality="1080p 全高清", cookie_file="")
        assert settings.save_settings(payload) is True
        loaded = settings.load_settings()
        assert loaded["quality"] == "1080p 全高清"
        assert loaded["cookie_file"] == ""

    def test_creates_directory(self, isolated_settings):
        assert not isolated_settings.exists()
        settings.save_settings(dict(settings.DEFAULTS))
        assert (isolated_settings / "settings.json").is_file()

    def test_chinese_written_verbatim(self, isolated_settings):
        # ensure_ascii=False：文件里应保留中文原文，而不是 \uXXXX 转义。
        settings.save_settings(dict(settings.DEFAULTS))
        raw = (isolated_settings / "settings.json").read_text(encoding="utf-8")
        assert "不读取浏览器 Cookie" in raw

    def test_unwritable_target_returns_false(self, tmp_path, monkeypatch):
        blocker = tmp_path / "占位文件"
        blocker.write_text("占位", encoding="utf-8")
        bogus_dir = blocker / "nested"  # 父级是文件，mkdir 必然失败
        monkeypatch.setattr(settings, "SETTINGS_DIR", bogus_dir)
        monkeypatch.setattr(settings, "SETTINGS_FILE", bogus_dir / "settings.json")
        assert settings.save_settings(dict(settings.DEFAULTS)) is False
