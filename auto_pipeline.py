# 檔案路徑: auto_pipeline.py
import os
import sys
import subprocess
import calendar
from datetime import datetime, timedelta
from core import config

def log(msg):
    """將執行紀錄寫入日誌檔，方便未來追蹤自動排程是否有成功執行"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    
    log_path = os.path.join(config.BASE_DIR, "auto_pipeline.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

import time

def run_with_retry(cmd, cwd, step_name, env=None, max_retries=3, delay=30):
    """具備失敗重試機制的執行器"""
    for attempt in range(1, max_retries + 1):
        log(f"▶ [{step_name}] 嘗試執行 (第 {attempt}/{max_retries} 次)...")
        result = subprocess.run(cmd, cwd=cwd, env=env)
        
        if result.returncode == 0:
            log(f"✅ [{step_name}] 執行成功！")
            return True
        else:
            log(f"⚠️ [{step_name}] 執行失敗 (代碼: {result.returncode})")
            if attempt < max_retries:
                log(f"⏳ 等待 {delay} 秒後進行重試...")
                time.sleep(delay)
            else:
                log(f"❌ [{step_name}] 已達最大重試次數，放棄執行此步驟。")
                return False

def main():
    log("="*50)
    log("🚀 啟動【每月全自動化排程】")
    log("="*50)
    
    # ==========================================
    # 智慧計算日期：精準鎖定「上個月一整個月」
    # 無論今天是幾號，永遠抓取「上個月 1 號」到「本月 1 號」
    # ==========================================
    today = datetime.now()
    
    # 本月 1 號 (作為結束日期)
    first_of_current = today.replace(day=1)
    
    # 上個月的最後一天
    last_of_prev = first_of_current - timedelta(days=1)
    
    # 上個月 1 號 (作為起始日期)
    first_of_prev = last_of_prev.replace(day=1)

    start_str = first_of_prev.strftime("%Y-%m-%d")
    end_str = first_of_current.strftime("%Y-%m-%d")

    log(f"📅 目標擷取區間: {start_str} 至 {end_str} (精準鎖定上個月)")

    # --------------------------------------------------
    # 步驟 1: 感測器 API 抓取 (Go 語言模組)
    # --------------------------------------------------
    api_exe = os.path.join(config.API_SCRIPT_DIR, "api_fetcher.exe")
    if os.path.exists(api_exe):
        cmd = [api_exe, start_str, end_str, "30", "10", "ALL"]
        run_with_retry(cmd, config.API_SCRIPT_DIR, "步驟 1: 感測器 API 抓取")
    else:
        log(f"❌ [步驟 1 失敗] 找不到 {api_exe}")

    # --------------------------------------------------
    # 步驟 2: 數據空缺檢測與自動補 0 (Go 語言模組)
    # --------------------------------------------------
    checker_exe = os.path.join(config.API_SCRIPT_DIR, "data_checker.exe")
    if os.path.exists(checker_exe):
        cmd = [checker_exe, start_str, end_str, "auto_fix"]
        run_with_retry(cmd, config.API_SCRIPT_DIR, "步驟 2: 數據檢測與自動補零")
    else:
        log(f"❌ [步驟 2 失敗] 找不到 {checker_exe}")

    # --------------------------------------------------
    # 步驟 3: 台電帳單爬蟲 (Python 模組)
    # --------------------------------------------------
    scraper_py = os.path.join(config.SCRAPER_SCRIPT_DIR, "electricity_bill_scraper_v3.py")
    if os.path.exists(scraper_py):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        cmd = [sys.executable, scraper_py, "3"]
        run_with_retry(cmd, config.SCRAPER_SCRIPT_DIR, "步驟 3: 台電帳單網頁爬蟲", env=env)
    else:
        log(f"❌ [步驟 3 失敗] 找不到 {scraper_py}")

    log("="*50)
    log("🎉 【每月全自動化排程】完美執行完畢！")
    log("="*50 + "\n")

if __name__ == "__main__":
    main()