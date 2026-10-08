@echo off
title Hospital Dashboard
echo ============================================
echo   HospVision Dashboard
echo ============================================
echo.
cd /d "%~dp0"

echo Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python not found!
    pause
    exit /b 1
)

echo.
echo Starting Streamlit on http://localhost:8501
echo Keep this window open while using the dashboard.
echo.
python -m streamlit run app.py --server.port 8501 --server.headless false --server.address localhost

echo.
echo ============================================
echo  Server stopped or crashed. See error above.
echo ============================================
pause
