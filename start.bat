@echo off
title A股量化选股系统
cd /d "%~dp0"
echo.
echo   A股量化选股系统
echo   http://localhost:8501
echo.
py -m streamlit run app.py --server.port 8501
pause
