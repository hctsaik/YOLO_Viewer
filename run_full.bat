@echo off
chcp 65001 >nul
REM Full interactive viewer. This mode uses Streamlit /component/ iframes and may
REM be blocked by a corporate proxy, antivirus, CSP, or endpoint protection.
cd /d "%~dp0"
set CVR_SAFE_MODE=0
start "CV_Viewer server (full mode)" /min cmd /c "set CVR_SAFE_MODE=0&& python -m streamlit run 5_PG_Develop\app.py --server.port 8501"
echo Waiting for CV_Viewer (full mode) at http://localhost:8501 ...
:wait
timeout /t 1 /nobreak >nul
powershell -Command "try{(New-Object Net.Sockets.TcpClient('127.0.0.1',8501)).Close();exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto wait
start "" "http://localhost:8501"
