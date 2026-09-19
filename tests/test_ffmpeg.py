"""FFmpeg 便携安装与定位逻辑的单元测试（不访问网络）。"""

from __future__ import annotations

import zipfile

import pytest

from bili_dl import utils
from bili_dl.gui import ffmpeg_curl_command


def test_curl_command_keeps_progress_output():
    """-s 会关闭进度输出，导致界面永远拿不到进度——必须与 --progress-bar 互斥。"""
    command = ffmpeg_curl_command("x.zip")
    assert "-s" not in command and "-fsSL" not in command and "-sS" not in command
    assert "--progress-bar" in command
    assert "-fL" in command  # HTTP 错误 fail + 跟随跳转
    assert command[-1].startswith("https://")


def test_curl_command_revocation_flag_and_fallback():
    """默认带 --ssl-no-revoke（Watt 等中间人代理下 Schannel 吊销检查必失败）；降级变体不带。"""
    assert "--ssl-no-revoke" in ffmpeg_curl_command("x.zip")
    fallback = ffmpeg_curl_command("x.zip", with_revoke_flag=False)
    assert "--ssl-no-revoke" not in fallback
    assert fallback[-1] == ffmpeg_curl_command("x.zip")[-1]  # 下载地址一致


class TestFfmpegBinPath:
    def test_prefers_portable_install(self, tmp_path, monkeypatch):
        portable = tmp_path / "portable" / "bin" / "ffmpeg.exe"
        portable.parent.mkdir(parents=True)
        portable.write_bytes(b"fake")
        monkeypatch.setattr(utils, "FFMPEG_PORTABLE_DIR", tmp_path / "portable")
        monkeypatch.setattr(utils.shutil, "which", lambda name: r"C:\system\ffmpeg.exe")
        assert utils.ffmpeg_bin_path() == portable

    def test_falls_back_to_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "FFMPEG_PORTABLE_DIR", tmp_path / "absent")
        monkeypatch.setattr(utils.shutil, "which", lambda name: r"C:\system\ffmpeg.exe")
        assert utils.ffmpeg_bin_path() == utils.Path(r"C:\system\ffmpeg.exe")

    def test_none_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(utils, "FFMPEG_PORTABLE_DIR", tmp_path / "absent")
        monkeypatch.setattr(utils.shutil, "which", lambda name: None)
        assert utils.ffmpeg_bin_path() is None


class TestInstallFfmpegFromZip:
    @staticmethod
    def _make_ffmpeg_zip(path, exe_name="ffmpeg.exe"):
        """构造 Gyan.FD 结构的最小 zip：顶层目录/bin/ffmpeg.exe。"""
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"ffmpeg-9.0.1-essentials_build/bin/{exe_name}", b"fake-exe")
            archive.writestr("ffmpeg-9.0.1-essentials_build/bin/avcodec-61.dll", b"fake-dll")
            archive.writestr("ffmpeg-9.0.1-essentials_build/README.txt", b"readme")

    def test_installs_bin_directory(self, tmp_path):
        zip_path = tmp_path / "ffmpeg.zip"
        self._make_ffmpeg_zip(zip_path)
        target = tmp_path / "ffmpeg"

        bin_dir = utils.install_ffmpeg_from_zip(zip_path, target)

        assert bin_dir == target / "bin"
        assert (target / "bin" / "ffmpeg.exe").is_file()
        assert (target / "bin" / "avcodec-61.dll").is_file()
        assert not (target / "bin" / "README.txt").exists()  # 只复制 bin 目录

    def test_rejects_zip_without_ffmpeg(self, tmp_path):
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("random/file.txt", b"x")
        with pytest.raises(ValueError, match="未找到"):
            utils.install_ffmpeg_from_zip(zip_path, tmp_path / "out")

    def test_rejects_zip_slip_entries(self, tmp_path):
        zip_path = tmp_path / "evil.zip"
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("build/bin/ffmpeg.exe", b"fake")
            archive.writestr("../evil.txt", b"bad")
        with pytest.raises(ValueError, match="路径异常"):
            utils.install_ffmpeg_from_zip(zip_path, tmp_path / "out")

    def test_reinstall_replaces_old_directory(self, tmp_path):
        zip_path = tmp_path / "ffmpeg.zip"
        self._make_ffmpeg_zip(zip_path)
        target = tmp_path / "ffmpeg"
        utils.install_ffmpeg_from_zip(zip_path, target)
        (target / "bin" / "stale.txt").write_text("旧文件", encoding="utf-8")
        utils.install_ffmpeg_from_zip(zip_path, target)
        assert not (target / "bin" / "stale.txt").exists()  # 旧目录被整体替换
