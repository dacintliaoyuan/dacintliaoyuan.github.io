@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
if not "%~1"=="" goto command
python "%~dp0art_pipeline.py" status
if errorlevel 1 goto failed
echo.
echo 常用命令：art_pipeline.bat analyze / report / run / status
echo 查看说明：art-pipeline.md；查看全部命令：art_pipeline.bat --help
pause
exit /b 0
:command
python "%~dp0art_pipeline.py" %*
exit /b %errorlevel%
:failed
echo 队列不可用，请查看上面的具体原因。
pause
exit /b 1
