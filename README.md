# B站音视频分离下载器（bili-dl）

简体中文 | [English](README_EN.md)

[![CI](https://github.com/Diderde/bili-dl/actions/workflows/ci.yml/badge.svg)](https://github.com/Diderde/bili-dl/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows95)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
![Tests](https://img.shields.io/badge/tests-85%20passed-brightgreen)
![License](https://img.shields.io/badge/license-GPL--2.0--or--later-informational)

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的 B 站**视频流 / 音频流分离下载**工具，内置 HTTP 412 反爬应对，界面使用 [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)（深色 / 浅色 / 跟随系统主题）。

## 特性

- **分离下载**最佳视频流 + 音频流（默认，免 FFmpeg），或选择**合并为单文件**（需 FFmpeg：界面可**一键下载便携版**装到程序目录，也可官网下载或 winget 安装）
- 画质上限可选：480p（默认）/ 720p / 1080p / 最佳可用
- 现代 Chrome 请求头 + 请求节流，应对 HTTP 412 反爬
- 支持读取 Chrome / Edge / Firefox 登录 Cookie，或 Netscape 格式 cookies.txt
- 下载过程中可随时**取消**；进度条、速度、剩余时间实时显示
- 运行日志面板，警告与错误自动上浮到状态栏
- 常见故障（412、No video formats、Cookie 数据库锁定）自动翻译为可操作提示
- 设置自动记忆：画质、Cookie 来源、音视频处理模式、主题（存于 `%APPDATA%\bili_dl\settings.json`；**保存位置每次启动重置**为程序目录下的 `downloads` 子文件夹——相对路径、随程序走，可用「浏览」临时更换且不被记录）

> 说明：浏览器 TLS 指纹模拟（curl_cffi）仍内置，但默认关闭——实测 B 站当前风控下
> 开启它会导致 playurl 返回空格式列表；如需启用可在代码中把 `impersonate` 置为 `True`。

## 快速开始（推荐）

1. 保证 `run.bat`、`bootstrap.py`、`src/` 在同一目录。
2. 双击 `run.bat`。启动器先输出**环境与依赖检查清单**（Python / tkinter / yt-dlp / curl_cffi / customtkinter / bili_dl，以及可选的 ffmpeg）：全绿则顺手把 yt-dlp 更新到 nightly 并启动；缺项则自动重建环境后再次出清单。
3. 检查与安装详情保存在 `environment_report.txt`。

## 手动安装

```powershell
cd bilibili_downloader
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m bili_dl
```

安装后也可直接使用 `bili-dl` 命令启动。

## 使用说明

1. 粘贴 BV 号、av 号、bilibili.com 或 b23.tv 链接（可以直接粘贴包含链接的整段文字）。
2. 选择保存目录、画质上限与音视频处理方式（默认分离保存、免 FFmpeg；合并为单文件需系统已装 FFmpeg）。
3. 一切正常时保持「不读取浏览器 Cookie」即可；遇到 HTTP 412 时，先在 Chrome / Edge / Firefox 登录 B 站并确认能播放该视频，然后在「登录状态来源」中选择同一个浏览器再下载。
4. cookies.txt 与浏览器 Cookie **二选一**，不能同时使用。

## 遇到 HTTP 412？

1. 在所选浏览器中登录 B 站并打开该视频，确认浏览器可以播放；
2. 回到软件，在「登录状态来源」中选择同一个浏览器；
3. 不要同时使用 cookies.txt 与浏览器 Cookie；
4. 关闭浏览器无痕窗口，确认软件与浏览器使用同一网络；
5. 重新运行 `run.bat` 更新 yt-dlp 与 curl_cffi；
6. 避免短时间内连续重复下载同一视频。

## 遇到 No video formats found？

通常是 B 站改版导致 yt-dlp 解析器暂时跟不上：

1. 重新运行 `run.bat`——启动器会在装好依赖后自动把 yt-dlp 升级到 nightly 版；
2. 若仍失败，选择已登录的浏览器 Cookie 再试（部分内容需登录/大会员）；
3. 稍后再试，等待 yt-dlp 上游修复。

## 第三方依赖

直接依赖（其余随 pip 自动解析，各组件许可证以其自身仓库为准）：

| 组件 | 用途 | 许可证 |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 视频解析与下载内核 | Unlicense（公有领域） |
| [curl-cffi](https://github.com/lexiforest/curl-cffi) | 浏览器 TLS 指纹模拟能力（默认关闭，备用） | MIT |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | 现代化界面组件库 | MIT |

说明：本项目只分发源码，依赖均由用户侧 pip 从 PyPI 安装；`bootstrap.py` 仅在 pip 缺失时从 PyPA 官方地址下载 `get-pip.py`。本项目不内嵌、不修改任何第三方代码。

**可选外部组件**：合并为单文件模式需要 FFmpeg——推荐直接点界面里的「一键下载 FFmpeg」，程序会把便携版下载并解压到程序目录的 `ffmpeg\` 文件夹（无需管理员权限，删除该文件夹即卸载）；也可以从 [FFmpeg 官网](https://ffmpeg.org/download.html) 手动下载或执行 `winget install Gyan.FFmpeg`。默认的分离保存模式无需任何外部组件。

## 开发

```powershell
python -m pip install -e ".[dev]"
pytest          # 运行单元测试（不访问网络）
ruff check .    # 代码风格检查
```

## 项目结构

```
bilibili_downloader/
├── run.bat                  # 一键启动入口
├── bootstrap.py             # 环境自举：搜 Python、建 venv、装依赖（仅标准库）
├── pyproject.toml           # 打包与工具链配置
├── src/bili_dl/
│   ├── __main__.py          # python -m bili_dl 入口
│   ├── gui.py               # CustomTkinter 界面
│   ├── core.py              # 下载引擎（yt-dlp 选项组装、取消、进度）
│   ├── settings.py          # 用户设置持久化
│   ├── utils.py             # 链接归一化、错误信息翻译等纯函数
│   └── constants.py         # 常量：请求头、画质/Cookie 选项等
└── tests/                   # 单元测试
```

## 说明

本项目代码以 [GPL-2.0-or-later](LICENSE) 许可开源：任何修改后再分发的版本必须同样以 GPL-2.0+ 开源并保留版权声明。使用时请遵守 B 站用户协议；下载内容请勿用于商业用途。
