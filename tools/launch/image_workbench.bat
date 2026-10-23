@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
title 图片工作台
cd /d "%~dp0..\.."
set "PORT=8765"

where python >nul 2>nul
if errorlevel 1 (
  echo 没有找到 python。请先安装 Python 3，并勾选“添加到 PATH”。
  pause
  exit /b 1
)

echo 图片工作台：http://127.0.0.1:%PORT%/
echo 关闭这个窗口即可停止工作台。
python tools\image_workbench.py --port %PORT%
if errorlevel 1 (
  echo 工作台启动失败，请核对上面的错误信息。
  pause
)
