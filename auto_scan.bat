@echo off
chcp 65001 >nul
title A股量化-自动扫描
cd /d "%~dp0"

echo [%date% %time%] 自动扫描开始...
echo.

:: 运行无头扫描脚本
py scan_headless.py

:: 记录日志
echo [%date% %time%] 扫描完成 >> scan_log.txt

:: 如果Python脚本异常退出，记录错误
if %errorlevel% neq 0 (
    echo [%date% %time%] 扫描失败，错误码: %errorlevel% >> scan_error.log
)
