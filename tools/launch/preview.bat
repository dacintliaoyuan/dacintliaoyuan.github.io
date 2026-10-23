@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
title 个人主页预览
cd /d "%~dp0..\.."
set "PORT=8766"
set "URL=http://127.0.0.1:%PORT%/"

where python >nul 2>nul
if errorlevel 1 (
  echo 没有找到 python。请先安装 Python 3，并勾选“添加到 PATH”。
  pause
  exit /b 1
)

rem 第一次运行，或带 rebuild 参数（改过 site/config/pool.txt 之后）时，先从本机图库生成图片素材。
if /i "%~1"=="rebuild" goto build
if not exist "site\assets\manifest.json" goto build
goto serve

:build
echo 正在使用已验收背景生成网站素材……
if exist "site\assets\manifest.json" (
  python tools\build_assets.py --reuse-sky
) else (
  python tools\build_assets.py
)
if errorlevel 1 (
  echo 素材生成失败。已有素材保留；请核对整图验收或人工遮罩审核及上面的错误信息。
  pause
  exit /b 1
)

:serve
rem 端口已经在监听时，多半是之前开着的预览，直接打开浏览器即可。
netstat -ano | findstr /r /c:"127.0.0.1:%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo 预览已经在运行，正在打开浏览器：%URL%
  start "" "%URL%"
  exit /b 0
)
echo 预览地址：%URL%
echo 关闭这个窗口即可停止预览。
start "" /min cmd /c "timeout /t 1 /nobreak >nul & start "" "%URL%""
rem 预览服务让浏览器每次都检查有没有新版本，改完代码按普通刷新就能看到。
python tools\serve.py %PORT%
