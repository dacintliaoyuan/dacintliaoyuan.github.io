@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
title 个人主页人工素材处理
where python >nul 2>nul
if errorlevel 1 (
  echo 没有找到 Python 3，请先安装并添加到 PATH。
  exit /b 1
)
if "%~1"=="" (
  echo 使用方法：prepare_scenes.bat prepare --input manual-input/scenes.json
  echo 检查遮罩叠加图后：prepare_scenes.bat approve --id "场景id" --reviewer "审核者" --note "检查结果"
  echo 检查全部素材：prepare_scenes.bat validate
  exit /b 0
)
python "%~dp0prepare_scenes.py" %*
exit /b %errorlevel%
