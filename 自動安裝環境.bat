@echo off
:: 設定 CMD 視窗支援 UTF-8 中文顯示，避免亂碼
chcp 65001 >nul

echo ===================================================
echo      ⚡ 能源管理自動化系統 - 首次環境安裝程式
echo ===================================================
echo.
echo 正在尋找您電腦中的 Anaconda / Miniconda...

:: 智慧尋找 Anaconda 路徑
set "CONDA_ACTIVATE="
if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat" set "CONDA_ACTIVATE=%USERPROFILE%\anaconda3\Scripts\activate.bat"
if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat" set "CONDA_ACTIVATE=%USERPROFILE%\miniconda3\Scripts\activate.bat"
if exist "C:\ProgramData\anaconda3\Scripts\activate.bat" set "CONDA_ACTIVATE=C:\ProgramData\anaconda3\Scripts\activate.bat"
if exist "C:\anaconda3\Scripts\activate.bat" set "CONDA_ACTIVATE=C:\anaconda3\Scripts\activate.bat"

:: 如果都找不到，提示錯誤並退出
if "%CONDA_ACTIVATE%"=="" (
    echo.
    echo [❌ 錯誤] 找不到 Anaconda 啟動程式！
    echo 請確保您已安裝 Anaconda 或 Miniconda，並且安裝在預設路徑。
    echo.
    pause
    exit /b
)

echo ✅ 找到 Anaconda： %CONDA_ACTIVATE%
echo.
echo ===================================================
echo 準備建立 Python 虛擬環境 (scraper_env)，這可能需要幾分鐘...
echo ===================================================
echo.

:: 呼叫 Anaconda 並建立環境
call "%CONDA_ACTIVATE%"
call conda create -n scraper_env python=3.9 -y

echo.
echo ===================================================
echo 準備安裝系統必備套件 (requirements.txt)...
echo ===================================================
echo.

:: 啟動虛擬環境並安裝套件
call conda activate scraper_env
call pip install -r requirements.txt

echo.
echo ===================================================
echo 🎉 安裝全部完成！
echo.
echo 請關閉此黑色的安裝視窗。
echo 以後您只需要雙擊專案資料夾中的【能源管理中控台.exe】即可啟動系統！
echo ===================================================
pause