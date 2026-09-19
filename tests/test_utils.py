"""bili_dl.utils 纯函数的单元测试（不访问网络）。"""

from __future__ import annotations

import pytest

from bili_dl.utils import (
    clean_error_message,
    default_save_dir,
    detect_media_kind,
    human_bytes,
    normalize_source,
)


class TestDefaultSaveDir:
    def test_is_downloads_subfolder_of_working_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert default_save_dir() == tmp_path / "downloads"

    def test_always_named_downloads(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert default_save_dir().name == "downloads"


class TestNormalizeSource:
    def test_bv_id_becomes_url(self):
        assert normalize_source("BV1xjNq67eWt") == "https://www.bilibili.com/video/BV1xjNq67eWt"

    def test_lowercase_bv_normalizes_prefix(self):
        assert normalize_source("bv1xjNq67eWt") == "https://www.bilibili.com/video/BV1xjNq67eWt"

    def test_bv_extracted_from_sentence(self):
        assert (
            normalize_source("看看这个 BV1xjNq67eWt 呀")
            == "https://www.bilibili.com/video/BV1xjNq67eWt"
        )

    def test_av_number(self):
        assert normalize_source("av170001") == "https://www.bilibili.com/video/av170001"

    def test_av_extracted_from_sentence(self):
        assert normalize_source("av170001 前后有字") == "https://www.bilibili.com/video/av170001"

    def test_full_url_passthrough(self):
        url = "https://www.bilibili.com/video/BV1xjNq67eWt?p=1"
        assert normalize_source(url) == url

    def test_short_link_passthrough(self):
        assert normalize_source("https://b23.tv/abc123") == "https://b23.tv/abc123"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="请输入"):
            normalize_source("   ")

    def test_foreign_host_raises(self):
        with pytest.raises(ValueError, match="bilibili"):
            normalize_source("https://www.youtube.com/watch?v=1")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="未识别"):
            normalize_source("随便输入的一段文本")


class TestHumanBytes:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "0.0 B"),
            (1023.4, "1023.4 B"),
            (2048, "2.0 KiB"),
            (1024**2, "1.0 MiB"),
            (3 * 1024**3, "3.0 GiB"),
            (5 * 1024**4, "5120.0 GiB"),
        ],
    )
    def test_formats(self, value, expected):
        assert human_bytes(value) == expected


class TestDetectMediaKind:
    @pytest.mark.parametrize(
        ("vcodec", "acodec", "expected"),
        [
            ("avc1", "none", "视频流"),
            ("none", "mp4a", "音频流"),
            ("avc1", "mp4a", "媒体文件"),
            (None, None, "媒体文件"),
        ],
    )
    def test_kinds(self, vcodec, acodec, expected):
        assert detect_media_kind({"vcodec": vcodec, "acodec": acodec}) == expected


class TestCleanErrorMessage:
    def test_412_gets_guidance(self):
        message = clean_error_message("ERROR: HTTP Error 412: Precondition Failed")
        assert "412" in message
        assert "浏览器" in message

    def test_cookie_db_error(self):
        message = clean_error_message("ERROR: could not copy Chrome cookie database")
        assert "cookies.txt" in message

    def test_impersonate_error(self):
        message = clean_error_message("ERROR: impersonate target 'chrome' is not available")
        assert "模拟" in message

    def test_no_video_formats_error(self):
        message = clean_error_message("ERROR: [BiliBili] BV1xx: No video formats found!")
        assert "nightly" in message
        assert "浏览器" in message

    def test_ffmpeg_missing_error(self):
        message = clean_error_message(
            "ERROR: You have requested merging of multiple formats but ffmpeg is not installed"
        )
        assert "FFmpeg" in message
        assert "分离保存" in message

    def test_network_timeout_error(self):
        message = clean_error_message(
            "ERROR: [download] Got error: Read timed out.. Giving up after 8 retries"
        )
        assert "重试" in message
        assert "PCDN" in message

    def test_plain_error_stripped(self):
        assert clean_error_message("ERROR: something broke") == "something broke"

    def test_empty_gets_fallback(self):
        assert "下载失败" in clean_error_message("  ")
