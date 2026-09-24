@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem Success by default; every launcher branch below only flips RC to 1 on failure.
rem Do not use %ERRORLEVEL% inside parenthesised blocks: cmd expands it at parse time.
set "RC=0"
title B站下载器 (bili-dl) - 环境检查与依赖检查

echo ============================================================
echo B站下载器：环境检查与依赖检查，通过后自动启动
echo ============================================================
echo.

set "BOOTSTRAP=%~dp0bootstrap.py"
if not exist "%BOOTSTRAP%" (
    echo [错误] 未找到 bootstrap.py
    echo 请将 run.bat、bootstrap.py、pyproject.toml 与 src 文件夹放在同一目录。
    pause
    exit /b 1
)

if not exist "%~dp0src\bili_dl" (
    echo [错误] 未找到 src\bili_dl 包目录
    echo 请将 run.bat、bootstrap.py、pyproject.toml 与 src 文件夹放在同一目录。
    pause
    exit /b 1
)

rem Any interpreter able to run bootstrap.py is enough here.
rem bootstrap.py re-scans all usable Pythons itself before creating the venv.
where py.exe >nul 2>nul
if not errorlevel 1 (
    py -3 "%BOOTSTRAP%"
    if errorlevel 1 set "RC=1"
    goto :finish
)

where python.exe >nul 2>nul
if not errorlevel 1 (
    python "%BOOTSTRAP%"
    if errorlevel 1 set "RC=1"
    goto :finish
)

where python3.exe >nul 2>nul
if not errorlevel 1 (
    python3 "%BOOTSTRAP%"
    if errorlevel 1 set "RC=1"
    goto :finish
)

rem PATH 中没有 Python 时，再检查几个常见位置。
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "C:\Python313\python.exe"
    "D:\Python313\python.exe"
    "C:\Python312\python.exe"
    "D:\Python312\python.exe"
    "D:\python.exe"
) do (
    if exist "%%~P" (
        "%%~P" "%BOOTSTRAP%"
        if errorlevel 1 set "RC=1"
        goto :finish
    )
)

echo [错误] 完全没有找到能够启动 bootstrap.py 的 Python。
echo 请先安装 64 位 Python 3.10 或更新版本（推荐 3.13），并在安装器中勾选：
echo   1. pip
echo   2. Tcl/Tk and IDLE
echo   3. py launcher
echo   4. Add Python to PATH
echo.
set "RC=1"

:finish
if not "%RC%"=="0" (
    echo.
    echo 启动失败。请打开同目录下的 environment_report.txt 查看具体原因。
    pause
)
exit /b %RC%
