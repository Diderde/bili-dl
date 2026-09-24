# -*- coding: utf-8 -*-
# Copyright (C) 2026 Diderde
# SPDX-License-Identifier: GPL-3.0-only
"""Bilibili downloader environment bootstrapper (Windows, stdlib only).

Searches for a usable CPython, creates .venv, installs the project in
editable mode (yt-dlp + curl_cffi + customtkinter) and launches
``python -m bili_dl``.
"""

import contextlib
import glob
import json
import os
import re
import shutil
import string
import subprocess
import sys
import traceback
from pathlib import Path

MIN_VERSION = (3, 10)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

ROOT = Path(__file__).resolve().parent
APP_PACKAGE_DIR = ROOT / "src" / "bili_dl"
VENV = ROOT / ".venv"
REPORT = ROOT / "environment_report.txt"
LOG = []


def write(message=""):
    text = str(message)
    print(text, flush=True)
    LOG.append(text)
    with contextlib.suppress(OSError):
        REPORT.write_text("\n".join(LOG) + "\n", encoding="utf-8")


def run_step(command, timeout=300):
    """以参数列表形式运行子进程命令（不经过 shell），输出记录到日志。"""
    command = [str(item) for item in command]
    write("$ " + subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.stdout:
        write(result.stdout.rstrip())
    return result


def add_path(result, seen, value):
    if not value:
        return
    try:
        path = Path(str(value).strip().strip('"')).expanduser()
        if not path.is_file():
            return
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            seen.add(key)
            result.append(path)
    except OSError:
        pass


def registry_pythons():
    """只读枚举系统标准 Python 注册表项用于发现解释器。

    仅 OpenKey/EnumKey/QueryValueEx 读取 HKCU/HKLM 的
    Software\\Python\\PythonCore，本项目对注册表零写入。
    """
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    found = []
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for base in (r"Software\Python\PythonCore", r"Software\WOW6432Node\Python\PythonCore"):
            try:
                with winreg.OpenKey(root, base) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        version = winreg.EnumKey(key, index)
                        try:
                            with winreg.OpenKey(root, base + "\\" + version + "\\InstallPath") as install:
                                folder, _ = winreg.QueryValueEx(install, None)
                                found.append(str(Path(folder) / "python.exe"))
                        except OSError:
                            pass
            except OSError:
                pass
    return found


def launcher_pythons():
    py = shutil.which("py")
    if not py:
        return []
    found = []
    for option in ("-0p", "--list-paths"):
        try:
            result = subprocess.run(
                [py, option],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            found.extend(re.findall(r"[A-Za-z]:\\[^\r\n]*?python(?:w)?\.exe", result.stdout, re.I))
        except Exception:
            pass
    return found


def common_pythons():
    env = os.environ
    patterns = [
        os.path.join(env.get("LOCALAPPDATA", ""), "Programs", "Python", "Python*", "python.exe"),
        os.path.join(env.get("ProgramFiles", r"C:\Program Files"), "Python*", "python.exe"),
        os.path.join(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "Python*", "python.exe"),
        os.path.join(env.get("USERPROFILE", ""), "miniconda3", "python.exe"),
        os.path.join(env.get("USERPROFILE", ""), "anaconda3", "python.exe"),
    ]
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = letter + ":\\"
            if os.path.exists(drive):
                patterns.extend(
                    [
                        drive + r"Python*\python.exe",
                        drive + r"Miniconda*\python.exe",
                        drive + r"Anaconda*\python.exe",
                    ]
                )
    found = []
    for pattern in patterns:
        if pattern:
            found.extend(glob.glob(pattern))
    return found


def find_python_files():
    result, seen = [], set()
    add_path(result, seen, sys.executable)

    for variable in ("PYTHON", "VIRTUAL_ENV", "CONDA_PREFIX"):
        value = os.environ.get(variable)
        if variable in ("VIRTUAL_ENV", "CONDA_PREFIX") and value:
            value = str(Path(value) / "python.exe")
        add_path(result, seen, value)

    for command in ("python", "python3"):
        add_path(result, seen, shutil.which(command))
    for path in launcher_pythons() + registry_pythons() + common_pythons():
        add_path(result, seen, path)
    return result


PROBE = r'''
import importlib.util, json, platform, struct, sys

def has(name):
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False

print(json.dumps({
    "exe": sys.executable,
    "version": list(sys.version_info[:3]),
    "version_text": sys.version.split()[0],
    "impl": platform.python_implementation(),
    "bits": struct.calcsize("P") * 8,
    "tk": has("tkinter"),
    "venv": has("venv"),
    "pip": has("pip"),
    "ensurepip": has("ensurepip")
}))
'''


def probe(path):
    try:
        result = subprocess.run(
            [str(path), "-I", "-c", PROBE],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        for line in reversed(result.stdout.splitlines()):
            try:
                return json.loads(line), ""
            except json.JSONDecodeError:
                pass
        return None, result.stdout.strip()
    except Exception as error:
        return None, str(error)


DEPENDENCY_PROBE = r'''
import importlib
import importlib.metadata as metadata
import json
import sys

names = {"yt_dlp": "yt-dlp", "curl_cffi": "curl-cffi",
         "customtkinter": "customtkinter", "bili_dl": "bili-dl"}
report = {"python": sys.version.split()[0]}
for module_name, dist_name in names.items():
    try:
        module = importlib.import_module(module_name)
        version = getattr(module, "__version__", None)
        if not version:
            version = metadata.version(dist_name)
        report[module_name] = str(version)
    except Exception:
        report[module_name] = None
try:
    import tkinter
    report["tkinter"] = True
except Exception:
    report["tkinter"] = False
print(json.dumps(report))
'''


def check_dependencies(python):
    """在给定解释器中逐项检查运行依赖，返回 (全部就绪, report 字典)。"""
    result = subprocess.run(
        [str(python), "-I", "-c", DEPENDENCY_PROBE],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                report = json.loads(line)
            except json.JSONDecodeError:
                continue
            required = ("yt_dlp", "curl_cffi", "customtkinter", "bili_dl")
            all_ok = report.get("tkinter") and all(report.get(name) for name in required)
            return bool(all_ok), report
    return False, {}


def report_environment(dep_report):
    """把依赖检查结果逐项写入日志。"""
    write("环境与依赖检查结果：")
    write("  Python 解释器 : {}".format(dep_report.get("python", "?")))
    write("  tkinter       : {}".format("可用" if dep_report.get("tkinter") else "缺失"))
    for module_name in ("yt_dlp", "curl_cffi", "customtkinter", "bili_dl"):
        version = dep_report.get(module_name)
        write("  {:<13} : {}".format(module_name, version if version else "缺失"))
    if shutil.which("ffmpeg"):
        write("  ffmpeg（可选）: 已检测到，可使用合并模式")
    else:
        write("  ffmpeg（可选）: 未检测到（分离模式不受影响；合并模式需另行安装）")


def compatible(info):
    if info["impl"] != "CPython":
        return False, "不是 CPython"
    if tuple(info["version"]) < MIN_VERSION:
        return False, "版本低于 3.10"
    if not info["tk"]:
        return False, "缺少 tkinter"
    if not info["venv"]:
        return False, "缺少 venv"
    return True, ""


def search_usable_pythons():
    candidates = []
    files = find_python_files()
    write("共发现 {} 个 Python 路径。".format(len(files)))

    for path in files:
        info, error = probe(path)
        if not info:
            write("[不可用] {} -> {}".format(path, error))
            continue
        ok, reason = compatible(info)
        status = "候选" if ok else "跳过"
        write(
            "[{}] {} | {} | {}位 | tkinter={} | venv={} | pip={} | ensurepip={}{}".format(
                status,
                info["exe"],
                info["version_text"],
                info["bits"],
                info["tk"],
                info["venv"],
                info["pip"],
                info["ensurepip"],
                " | " + reason if reason else "",
            )
        )
        if ok:
            candidates.append((Path(info["exe"]), info))

    # Prefer 3.13/3.12/3.11/3.10 for broad wheel compatibility; then newer versions.
    order = {13: 100, 12: 95, 11: 90, 10: 85, 14: 80, 15: 60}
    candidates.sort(
        key=lambda item: (
            order.get(item[1]["version"][1], 50),
            item[1]["bits"],
            item[1]["ensurepip"],
            item[1]["version"][2],
        ),
        reverse=True,
    )
    return candidates


def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def imports_work(python):
    result = subprocess.run(
        [str(python), "-I", "-c", "import bili_dl, customtkinter, tkinter, yt_dlp, curl_cffi; print('OK')"],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return result.returncode == 0, result.stdout.strip()


def download_get_pip(target):
    """从 PyPA 官方固定地址下载 get-pip.py（编译期常量，不接受任何外部输入）。"""
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("系统缺少 curl.exe（Windows 10 1803+ 自带），无法下载 get-pip.py")
    args = [curl, "-fsSL", "--retry", "3", "-o", str(target), GET_PIP_URL]
    if run_step(args, 300).returncode != 0:
        raise RuntimeError("get-pip.py 下载失败")


def install_pip(python):
    if run_step([python, "-m", "pip", "--version"], 60).returncode == 0:
        return

    write("pip 缺失，先尝试 ensurepip……")
    run_step([python, "-m", "ensurepip", "--upgrade", "--default-pip"], 180)
    if run_step([python, "-m", "pip", "--version"], 60).returncode == 0:
        return

    write("ensurepip 失败，下载 PyPA 官方 get-pip.py……")
    target = ROOT / "get-pip.py"
    try:
        download_get_pip(target)
        if len(target.read_bytes()) < 10000:
            raise RuntimeError("get-pip.py 下载内容异常")
        if run_step([python, target], 600).returncode != 0:
            raise RuntimeError("get-pip.py 执行失败")
    finally:
        with contextlib.suppress(OSError):
            target.unlink()

    if run_step([python, "-m", "pip", "--version"], 60).returncode != 0:
        raise RuntimeError("pip 自动修复失败")


def upgrade_ytdlp_nightly(runtime):
    """把 yt-dlp 升级到 nightly，并校验升级后依赖是否仍完整。

    B 站改版频繁，稳定版常常滞后（表现为 No video formats found）；
    升级失败不阻塞，稳定版仍可尝试下载。返回 True 表示环境仍然可用。
    """
    # eager：不加它时 pip 默认 only-if-needed，已满足约束的 curl_cffi 不会跟着升级，
    # 而 412 排障恰恰依赖 curl_cffi 也是新的（README「重新运行 run.bat 更新两者」）。
    command = [
        runtime,
        "-m",
        "pip",
        "install",
        "-U",
        "--upgrade-strategy",
        "eager",
        "--pre",
        "yt-dlp[default,curl-cffi]",
    ]
    try:
        result = run_step(command, 1200)
    except Exception as error:  # 超时、被杀软/占位进程锁住等
        write("yt-dlp 升级未完成（{}）；继续使用当前版本。".format(error))
        return True
    if result.returncode != 0:
        write("yt-dlp 升级返回退出码 {}；继续使用当前版本。".format(result.returncode))
        return True

    # 升级后才校验：半个失败的安装会让程序带着坏依赖启动，问题要到下载时才暴露。
    ok, details = imports_work(runtime)
    if not ok:
        write("升级后依赖校验未通过：{}".format(details))
        write("（程序仍会启动；若界面提示缺少依赖，请重新运行 run.bat 重建环境。）")
        return False
    write("yt-dlp 与 curl_cffi 已按 nightly 更新，依赖校验通过。")
    return True


def prepare_with(base_python):
    # 先把旧环境改名而不是直接删除：重建可能因为断网/代理失败，那时要把原环境放回去。
    # （删除不进回收站，而旧环境往往只是缺一个可选依赖，仍然可用。）
    backup = VENV.with_name(VENV.name + ".bak")
    if not VENV.exists() and backup.exists():
        backup.rename(VENV)  # 上一次重建失败留下的备份：先恢复，避免连备份一起丢掉
    if VENV.exists():
        shutil.rmtree(str(backup), ignore_errors=True)
        VENV.rename(backup)

    try:
        if run_step([base_python, "-m", "venv", str(VENV)], 300).returncode != 0:
            raise RuntimeError("创建 .venv 失败")

        runtime = venv_python()
        install_pip(runtime)
        run_step([runtime, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"], 900)
        # 以可编辑模式安装本项目（含 yt-dlp / curl_cffi / customtkinter 依赖）。
        # run_step() 固定 cwd=ROOT，传相对路径 "." 等价于项目根目录。
        editable_install = [runtime, "-m", "pip", "install", "-U", "-e", "."]
        if run_step(editable_install, 1800).returncode != 0:
            raise RuntimeError("安装项目与依赖失败（yt-dlp/curl_cffi/customtkinter）")
        upgrade_ytdlp_nightly(runtime)

        ok, details = imports_work(runtime)
        if not ok:
            raise RuntimeError("依赖验证失败：" + details)
        deps_ok, dep_report = check_dependencies(runtime)
        if not deps_ok:
            raise RuntimeError("依赖检查未全部通过：{}".format(dep_report))
    except Exception:
        # 重建失败：清掉半成品，把原有环境恢复回去，让用户至少还能用旧环境。
        shutil.rmtree(str(VENV), ignore_errors=True)
        if backup.exists():
            backup.rename(VENV)
            write("环境重建失败，已恢复原有的 .venv。")
        raise

    shutil.rmtree(str(backup), ignore_errors=True)
    report_environment(dep_report)
    return runtime


def launch(runtime):
    """用给定解释器后台启动 GUI 主程序（python -m bili_dl）。"""
    argv = [str(runtime), "-m", "bili_dl"]
    result = subprocess.run(
        argv,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        print(result.stdout, flush=True)
    return result.returncode


def main():
    write("B站下载器（bili-dl）环境检查与依赖检查")
    write("项目目录：{}".format(ROOT))

    if not APP_PACKAGE_DIR.is_dir():
        raise FileNotFoundError(
            "未找到 src\\bili_dl 包目录，请保证 run.bat、bootstrap.py、pyproject.toml 与 src/ 在同一目录。"
        )

    # 可编辑安装（prepare_with 里的 pip install -e .）依赖 pyproject.toml，
    # 提前检查，避免只在 pip 阶段报一个不好定位的错。
    if not (ROOT / "pyproject.toml").is_file():
        raise FileNotFoundError(
            "未找到 pyproject.toml，无法以可编辑模式安装本项目；"
            "请保证 run.bat、bootstrap.py、pyproject.toml 与 src/ 在同一目录。"
        )

    runtime = venv_python()
    if runtime.is_file():
        # 探测本身也可能失败（.venv 被杀软锁住、基础解释器失联、子进程超时），
        # 这类异常不该让自举直接中止——按「环境不可用」处理，转入重建流程。
        ok, deps_ok, dep_report, details = False, False, {}, ""
        try:
            ok, details = imports_work(runtime)
            if ok:
                deps_ok, dep_report = check_dependencies(runtime)
        except Exception as error:
            details = "{}: {}".format(type(error).__name__, error)

        if ok and deps_ok:
            report_environment(dep_report)
            write("环境与依赖检查通过，顺手把 yt-dlp 更新到 nightly……")
            upgrade_ytdlp_nightly(runtime)
            return launch(runtime)
        if ok:
            write("依赖检查发现缺失：")
            report_environment(dep_report)
            write("转入环境重建流程……")
        else:
            write("已有 .venv 已损坏或依赖不完整：{}".format(details))

    failures = []
    for base_python, _info in search_usable_pythons():
        try:
            write("\n尝试使用：{}".format(base_python))
            runtime = prepare_with(base_python)
            write("环境准备完成，正在启动程序。")
            return launch(runtime)
        except Exception as error:
            failures.append("{} -> {}".format(base_python, error))
            write("[失败] {}".format(failures[-1]))

    if not failures:
        raise RuntimeError("没有找到同时具备 Python 3.10+、tkinter 和 venv 的完整 CPython。")
    raise RuntimeError("所有 Python 候选均失败：\n" + "\n".join(failures))


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as error:
        write("\n启动失败：{}".format(error))
        write(traceback.format_exc())
        write("请查看：{}".format(REPORT))
        raise SystemExit(1) from error
