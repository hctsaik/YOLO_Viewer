@echo off
chcp 65001 >nul
REM 元件載入診斷頁(主 app 的 viewer/thumbwall 跳 "trouble loading the component" 時跑這個)。
REM 它不依賴自訂元件路徑,主 app 元件全掛它也能開;判讀說明就在頁面上。
cd /d "%~dp0"
start "CV_Viewer diagnose" /min cmd /c "python -m streamlit run 5_PG_Develop\diagnose_components.py --server.port 8502"
echo 正在等待診斷頁啟動(http://localhost:8502)...
:wait
timeout /t 1 /nobreak >nul
powershell -Command "try{(New-Object Net.Sockets.TcpClient('127.0.0.1',8502)).Close();exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto wait
start "" "http://localhost:8502"
