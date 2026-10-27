@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
title 更新 ABOUT
cd /d "%~dp0..\.."

where python >nul 2>nul
if errorlevel 1 (
  echo 没有找到 python。请先安装 Python 3，并勾选“添加到 PATH”。
  pause
  exit /b 1
)

rem 把 content\about.zh.md 和 content\about.en.md 写进 site\index.html。
rem 平时打开本机预览时会自动做这一步；这里是手动入口。
python tools\build_about.py
if errorlevel 1 (
  echo 请按上面的提示修改 md 文件，再运行一次。
  pause
  exit /b 1
)
pause
