# 檔案路徑: core/config.py
import os

# 自動抓取專案根目錄 (往上一層)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# --- 腳本與模組路徑 ---
API_SCRIPT_DIR = os.path.join(BASE_DIR, "Energy Report Automation")
SCRAPER_SCRIPT_DIR = os.path.join(BASE_DIR, "electricity_bill_scraper")

# --- 檔案與資料夾路徑 ---
API_EXCEL_PATH = os.path.join(API_SCRIPT_DIR, "店家ID.xlsx")
ACCOUNTS_CSV_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "accounts.csv")
OUTPUT_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "output")
HISTORY_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "歷史爬取資料")

# --- 離線瀏覽器路徑 ---
OFFLINE_CHROME_DIR = os.path.join(BASE_DIR, "GoogleChromePortable")
OFFLINE_DRIVER_DIR = os.path.join(BASE_DIR, "chromedriver-win64")

# --- UI 外觀預設值 ---
YEARS = [str(y) for y in range(2020, 2031)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]
THREADS = ["1", "3", "5", "10", "15", "20", "30"]
BROWSERS = ["1", "2", "3", "4", "5", "6", "8", "10"]