@echo off
chcp 65001 >nul
REM CV_Viewer 安全模式啟動(受限網路 / 元件跳 "trouble loading the component" 橫幅的機器用)。雙擊即可。
REM
REM 為什麼需要它:viewer / thumbwall 是 Streamlit「自訂元件」,瀏覽器必須另外抓 /component/ 資產、
REM 並在 iframe 內執行腳本、60 秒內回報 componentReady。某些機器上這條路被擋:
REM   A 類 = 內容過濾 proxy / 防火牆 / 防毒攔掉或拖慢 /component/ 資產;
REM   B 類 = 端點防護 / 瀏覽器政策封鎖 iframe 內的腳本。
REM 兩類都會讓元件永遠送不出 ready → 跳黃色橫幅、工作台不能用,而且『元件端程式碼修不了』。
REM
REM 安全模式完全不走那條路:縮圖牆與主 viewer 改成 server 端算繪的 st.image / st.button,
REM 瀏覽器只需要能顯示主頁(已知是好的)。代價:沒有拖曳縮放 / 框選 ROI / 點擊取像素值,
REM 縮放平移改用側欄滑桿。功能仍可判片、切圖、標記、比較、匯出。
REM
REM 進去後可在側欄「🛟 安全模式」關掉它,切回一般模式(若該機環境已修好)。
cd /d "%~dp0"
set CVR_SAFE_MODE=1
start "CV_Viewer server (safe mode)" /min cmd /c "set CVR_SAFE_MODE=1&& python -m streamlit run 5_PG_Develop\app.py --server.port 8501"
echo 正在等待服務啟動(安全模式,http://localhost:8501)...
:wait
timeout /t 1 /nobreak >nul
powershell -Command "try{(New-Object Net.Sockets.TcpClient('127.0.0.1',8501)).Close();exit 0}catch{exit 1}" >nul 2>&1
if errorlevel 1 goto wait
start "" "http://localhost:8501"
echo 已開啟瀏覽器(安全模式)。要停止服務請關閉「CV_Viewer server (safe mode)」視窗。
