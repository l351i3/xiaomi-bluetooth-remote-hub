@echo off
setlocal EnableExtensions
chcp 936 >nul 2>nul
title RemoteHub Windows 一键更新

set "BASE=http://T1_IP:8000"
set "PS1=%TEMP%\remotehub-update.ps1"

echo ================================================
echo   RemoteHub Windows 一键更新（双击运行即可）
echo ================================================
echo.
echo [1/3] 下载更新脚本 ...
del "%PS1%" >nul 2>nul
where curl.exe >nul 2>nul
if errorlevel 1 goto :use_ps_dl
curl.exe -fsSL --max-time 30 -o "%PS1%" "%BASE%/update-win-receiver.ps1"
if errorlevel 1 goto :dlfail
goto :dlcheck

:use_ps_dl
echo   curl.exe 不可用，改用 PowerShell 下载 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri '%BASE%/update-win-receiver.ps1' -OutFile '%PS1%'; exit 0 } catch { exit 1 }"
if errorlevel 1 goto :dlfail

:dlcheck
if not exist "%PS1%" goto :dlfail

echo [2/3] 执行更新（定位目录 / 备份 / 替换 / 重启 / 自检）...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -LiteralPath '%PS1%' -ErrorAction SilentlyContinue" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto :done
echo [3/3] 更新脚本返回码 %RC%（非 0 请先阅读上方输出；如遇策略拦截，参考 TASK-mic-switch.md 第 1B 节手动步骤）。
goto :end

:done
echo [3/3] 全部完成。

:end
echo.
echo 按任意键关闭本窗口 ...
pause >nul
endlocal
exit /b 0

:dlfail
echo.
echo [下载失败] 请依次检查：
echo   1. Windows 与 T1 盒子在同一局域网
echo   2. 浏览器访问 %BASE% 能否打开（打不开 = T1 分发服务未启动）
echo   3. 稍后重试；或将本窗口内容截图反馈
echo.
echo 按任意键关闭本窗口 ...
pause >nul
endlocal
exit /b 1
