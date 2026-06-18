⚡ 能源管理與自動化中控台 (Energy Management & Automation System)這是一個全方位的能源數據自動化收集與管理系統。本專案整合了 感測器 API 數據爬取 與 台電電子帳單網頁自動化爬蟲，並透過 Docker 容器化的 PostgreSQL 資料庫進行統一儲存，最後提供一個直覺的視覺化 GUI 中控台供使用者一鍵操作。✨ 核心特色 (Core Features)🖥️ GUI 視覺化中控台：使用 customtkinter 打造具備深/淺色模式的現代化操作介面，支援背景執行緒監控、單行進度條顯示與任務強制終止功能。📊 智能 API 串接與多執行緒：高速併發爬取感測器數據，並具備「自動降級重試」機制 (60天 -> 30天 -> 7天)，確保網路不穩時資料不遺漏。🌐 台電帳單自動化爬蟲：採用 undetected-chromedriver 搭配動態滑鼠軌跡模擬 (ActionChains)，智慧繞過 Cloudflare 的 Turnstile 互動式驗證，自動下載歷年用電度數並整理成 Tidy Data 格式。🐳 Docker 容器化資料庫：內建 docker-compose.yml 與 init.sql，一鍵啟動/關閉 PostgreSQL 伺服器，無需繁瑣的資料庫安裝設定。🔐 企業級資安防護：敏感資訊 (如資料庫密碼、API 金鑰) 皆透過 .env 環境變數抽離，搭配嚴謹的 .gitignore 確保機密不外洩。🛠️ 系統需求 (Prerequisites)在執行本專案之前，請確保您的電腦已安裝以下軟體：Python 3.9+ (建議使用 Anaconda 或 Miniconda 建立虛擬環境)Docker Desktop (用於啟動 PostgreSQL 資料庫)Google Chrome (網頁爬蟲需使用最新版 Chrome 瀏覽器)🚀 快速開始 (Quick Start)1. 專案環境設定首先，請將本專案複製到您的電腦，然後在終端機中建立並啟動一個新的虛擬環境。接著，透過以下指令一鍵安裝所有必備套件：# 透過 requirements.txt 自動安裝所有套件
pip install -r requirements.txt
2. 設定環境變數 (金鑰庫)複製專案根目錄下的 .env.example 檔案。將複製的檔案重新命名為 .env。打開 .env，填入您真實的資料庫密碼與 API URL。DB_HOST=localhost
DB_PORT=your_database_port
DB_NAME=energy_reports
DB_USER=admin
DB_PASS=您的超強密碼

API_URL=https://您的API網址/api/v1/tx

```

### 3. 準備店家與電號資料

* **感測器 API**：請於 `Energy Report Automation/店家ID.xlsx` 中填寫目標店家 ID。
* **台電爬蟲**：請於 `electricity_bill_scraper/accounts.csv` 中填寫要爬取的 `電號`、`用戶戶名`、`公司名稱`。

### 4. 啟動系統

若您有打包好的捷徑，可直接雙擊 `能源管理中控台.exe`。
若使用原始碼執行，請在終端機輸入：

```bash
python main_gui.py

```

1. 點擊介面上的 **「🐳 開啟節電資料儲存伺服器」** (Docker 會自動在背景建立資料庫並匯入 `init.sql` 藍圖)。
2. 根據需求設定「參數區」，並點擊對應的啟動按鈕進行資料爬取。

---

## 📁 專案結構 (Project Structure)

```text
Power App/
│
├── .env                  # 🔒 (需自行建立) 真實機密與環境變數
├── .env.example          # 📄 環境變數範本
├── .gitignore            # 🚫 Git 黑名單設定檔
├── docker-compose.yml    # 🐳 PostgreSQL 容器設定檔
├── init.sql              # 🗄️ 資料庫 Table 結構初始化腳本
├── launcher.py           # 🚀 專案啟動器 (可打包為 exe)
├── main_gui.py           # 🖥️ GUI 中控台主程式
├── requirements.txt      # 📦 專案必備套件清單
│
├── Energy Report Automation/   # 🔌 感測器 API 爬蟲模組
│   ├── sync_to_postgres_Multi-threading.py
│   ├── fetch_single_store.py
│   └── 店家ID.xlsx       # (需自行提供)
│
└── electricity_bill_scraper/   # 🌐 台電電子帳單爬蟲模組
    ├── electricity_bill_scraper_v3.py
    ├── merge_excel_files.py
    └── accounts.csv      # (需自行提供) 目標電號清單

⚠️ 注意事項與資安提醒請勿上傳真實資料：本專案的 .gitignore 已設定攔截 .env、pgdata/ (資料庫實體檔)、以及 output/ 產生的報表。請勿強制將這些包含真實客戶資料的檔案推送至公開的 GitHub。Chrome 版本匹配問題：爬蟲腳本會自動讀取系統登錄檔尋找您目前的 Chrome 版本以配對 WebDriver。若發生 session not created 錯誤，請先嘗試將您的 Google Chrome 瀏覽器更新至最新版本。資料視覺化：所有收集到的資料皆存入 PostgreSQL (power_consumption_records 資料表)。建議直接使用 Tableau 透過 localhost:5432 建立原生連線 (Live/Extract) 進行後續分析。