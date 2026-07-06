@echo off
chcp 65001 >nul
REM CV_Viewer 一鍵啟動(換機部署用)。雙擊即可。
REM 關鍵:一律用 http://localhost:8501 開 —— Chromium/Edge 對 localhost 有「隱含 proxy 繞過」,
REM 用機器 IP/主機名開則 proxy 會介入,公司內容過濾可把元件資產攔掉
REM (= 主頁正常、viewer/thumbwall 跳 "trouble loading the component" 橫幅;已實測重現,見 DEPLOYMENT.md)。
cd /d "%~dp0"
start "CV_Viewer server" /min cmd /c "python -m streamlit run 5_PG_Develop\app.py --server.port 8501"
echo 正在等待服務啟動(http://localhost:8501)...
:wait
timeout /t 1 /nobreak >nul
powershell -Command "try{(New-Object Net.Sockets.TcpClient('127.0.0.1',8501)).Close();exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto wait
start "" "http://localhost:8501"
echo 已開啟瀏覽器。要停止服務請關閉「CV_Viewer server」視窗。
