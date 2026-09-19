"""下载核心的单元测试：选项构造与取消机制（不访问网络）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from bili_dl.constants import DEFAULT_QUALITY, OUTPUT_TEMPLATE
from bili_dl.core import (
    DownloadCancelledByUser,
    DownloadEngine,
    DownloadRequest,
    build_ydl_options,
)


def make_request(tmp_path: Path, **overrides) -> DownloadRequest:
    values: dict = {
        "url": "https://www.bilibili.com/video/BV1xjNq67eWt",
        "save_dir": tmp_path,
        "quality_label": DEFAULT_QUALITY,
    }
    values.update(overrides)
    return DownloadRequest(**values)


class TestBuildYdlOptions:
    def test_default_quality_limit(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path))
        assert options["format"] == "bv,ba"
        assert options["format_sort"] == ["res:480"]

    def test_quality_choice(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, quality_label="1080p 全高清"))
        assert options["format_sort"] == ["res:1080"]

    def test_best_quality_has_empty_sort(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, quality_label="最佳可用画质"))
        assert options["format_sort"] == []

    def test_unknown_quality_falls_back(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, quality_label="不存在的选项"))
        assert options["format_sort"] == ["res:480"]

    def test_output_template(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path))
        assert OUTPUT_TEMPLATE in options["outtmpl"]
        assert str(tmp_path) in options["outtmpl"]

    def test_cookie_file_wins_over_browser(self, tmp_path):
        options = build_ydl_options(
            make_request(tmp_path, cookie_file="cookies.txt", browser_key="chrome")
        )
        assert options["cookiefile"] == "cookies.txt"
        assert "cookiesfrombrowser" not in options

    def test_browser_cookies_tuple(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, browser_key="edge"))
        assert options["cookiesfrombrowser"] == ("edge", None, None, None)

    def test_impersonate_disabled_by_flag(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, impersonate=False))
        assert "impersonate" not in options

    def test_default_request_disables_impersonate(self, tmp_path):
        # B 站当前风控下 TLS 模拟会导致 playurl 返回空格式，默认必须关闭。
        request = DownloadRequest(url="https://www.bilibili.com/video/BV1xjNq67eWt", save_dir=tmp_path)
        assert request.impersonate is False
        assert "impersonate" not in build_ydl_options(request)

    def test_merge_mode_format_spec(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path, merge=True))
        assert options["format"] == "bv*+ba/b"
        assert options["merge_output_format"] == "mp4"

    def test_default_is_separate_streams(self, tmp_path):
        options = build_ydl_options(make_request(tmp_path))
        assert options["format"] == "bv,ba"
        assert "merge_output_format" not in options

    def test_headers_not_shared_between_calls(self, tmp_path):
        first = build_ydl_options(make_request(tmp_path))
        first["http_headers"]["User-Agent"] = "changed"
        second = build_ydl_options(make_request(tmp_path))
        assert second["http_headers"]["User-Agent"] != "changed"


class TestEngineProgress:
    def test_overall_progress_spans_two_streams(self, tmp_path):
        seen: list[float] = []
        engine = DownloadEngine(
            make_request(tmp_path), on_progress=lambda percent, _text: seen.append(percent)
        )
        video_info = {"vcodec": "avc1", "acodec": "none"}
        audio_info = {"vcodec": "none", "acodec": "mp4a"}

        engine.progress_hook(
            {"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100, "info_dict": video_info}
        )
        engine.progress_hook(
            {"status": "finished", "info_dict": video_info, "filename": "video.m4s"}
        )
        engine.progress_hook(
            {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "info_dict": audio_info}
        )

        assert seen == [12.5, 50.0, 75.0]
        assert engine.files == ["video.m4s"]

    def test_estimate_only_total(self, tmp_path):
        seen: list[float] = []
        engine = DownloadEngine(
            make_request(tmp_path), on_progress=lambda percent, _text: seen.append(percent)
        )
        engine.progress_hook(
            {
                "status": "downloading",
                "downloaded_bytes": 10,
                "total_bytes_estimate": 40,
                "info_dict": {"vcodec": "none", "acodec": "mp4a"},
            }
        )
        assert seen == [12.5]

    def test_merge_mode_records_merged_output_via_pp_hook(self, tmp_path):
        """合并模式：下载钩子的流文件名不记录，最终文件由后处理钩子上报。"""
        seen: list[float] = []
        engine = DownloadEngine(
            make_request(tmp_path, merge=True), on_progress=lambda percent, _text: seen.append(percent)
        )
        media = {"vcodec": "avc1", "acodec": "mp4a"}
        engine.progress_hook(
            {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "info_dict": media}
        )
        engine.progress_hook({"status": "finished", "filename": "video.m4s", "info_dict": media})
        engine.progress_hook(
            {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100, "info_dict": media}
        )
        engine.progress_hook({"status": "finished", "filename": "audio.m4s", "info_dict": media})
        engine._postprocessor_hook(
            {"status": "finished", "info_dict": {"filepath": str(tmp_path / "out.mp4")}}
        )

        assert seen == [25.0, 50.0, 75.0, 100.0]
        assert engine.files == [str(tmp_path / "out.mp4")]

    def test_merge_mode_falls_back_to_downloaded_names(self, tmp_path):
        """"/b" 兜底选中单文件格式时后处理钩子不触发，应以下载记录为准。"""
        engine = DownloadEngine(make_request(tmp_path, merge=True))
        engine.progress_hook(
            {
                "status": "finished",
                "filename": str(tmp_path / "single.mp4"),
                "info_dict": {"vcodec": "avc1", "acodec": "mp4a"},
            }
        )
        assert engine.files == [str(tmp_path / "single.mp4")]


class TestCancellation:
    def test_cancelled_hook_raises(self, tmp_path):
        engine = DownloadEngine(make_request(tmp_path))
        engine.cancel()
        with pytest.raises(DownloadCancelledByUser):
            engine.progress_hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 1,
                    "total_bytes": 10,
                    "info_dict": {},
                }
            )

    def test_run_without_ytdlp_raises_runtime_error(self, tmp_path, monkeypatch):
        from bili_dl import core

        monkeypatch.setattr(core, "yt_dlp", None)
        engine = DownloadEngine(make_request(tmp_path))
        with pytest.raises(RuntimeError, match="yt-dlp"):
            engine.run()

    def test_run_merge_without_ffmpeg_raises(self, tmp_path, monkeypatch):
        from bili_dl import core

        monkeypatch.setattr(core, "ffmpeg_bin_path", lambda: None)
        engine = DownloadEngine(make_request(tmp_path, merge=True))
        with pytest.raises(RuntimeError, match="FFmpeg"):
            engine.run()

    def test_run_merge_passes_portable_ffmpeg_location(self, tmp_path, monkeypatch):
        """便携 FFmpeg 的 bin 目录应作为 ffmpeg_location 传给 yt-dlp。"""
        from bili_dl import core

        bin_dir = tmp_path / "ffmpeg" / "bin"
        monkeypatch.setattr(core, "ffmpeg_bin_path", lambda: bin_dir / "ffmpeg.exe")

        captured: dict = {}

        class FakeYDL:
            def __init__(self, opts):
                captured.update(opts)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def download(self, urls):
                return 0

        monkeypatch.setattr(core.yt_dlp, "YoutubeDL", FakeYDL)
        core.DownloadEngine(make_request(tmp_path, merge=True)).run()
        assert captured["ffmpeg_location"] == str(bin_dir)
