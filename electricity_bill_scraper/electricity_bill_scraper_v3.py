import pandas as pd
import time
import random
import os
import sys
import re
import math
from datetime import datetime
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoAlertPresentException
from concurrent.futures import ThreadPoolExecutor, as_completed

# 💡 新增：資料庫操作與環境變數套件
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

# --- 配置區 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_ROOT_DIR = os.path.dirname(BASE_DIR) # 往上一層回到 Power App 根目錄

# CSV 檔案路徑與輸出路徑
ACCOUNTS_CSV_PATH = os.path.join(BASE_DIR, 'accounts.csv')
OUTPUT_FOLDER_PATH = os.path.join(BASE_DIR, 'output')

# 💡 載入 .env 檔案中的資料庫連線資訊
ENV_PATH = os.path.join(APP_ROOT_DIR, ".env")
load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
if DB_HOST.lower() == "localhost":
    DB_HOST = "127.0.0.1" # 強制避開 IPv6 超時陷阱
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "energy_reports")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "admin_password")

# 💡 多執行緒與重試設定
DEFAULT_MAX_BROWSERS = 3     
MAX_RETRIES = 3              


# --- 核心邏輯區 ---

def get_chrome_major_version():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version_str, _ = winreg.QueryValueEx(key, "version")
        major_version = int(version_str.split('.')[0])
        return major_version
    except Exception:
        return None

def init_driver(worker_id):
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    
    custom_chrome_path = os.path.join(APP_ROOT_DIR, 'GoogleChromePortable', 'App', 'Chrome-bin', 'chrome.exe')
    custom_driver_path = os.path.join(APP_ROOT_DIR, 'chromedriver-win64', 'chromedriver.exe')
    
    if os.path.exists(custom_chrome_path) and os.path.exists(custom_driver_path):
        print(f"    [執行緒-{worker_id}] 啟動專屬離線版瀏覽器 (無視防火牆與版本更新)...")
        driver = uc.Chrome(
            options=options, 
            browser_executable_path=custom_chrome_path,
            driver_executable_path=custom_driver_path
        )
    else:
        print(f"    [執行緒-{worker_id}] ⚠️ 找不到離線瀏覽器資料夾，退回系統預設連線模式...")
        chrome_version = get_chrome_major_version()
        if chrome_version:
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            driver = uc.Chrome(options=options)
    
    window_width = 800
    window_height = 600
    
    if worker_id == 1:
        driver.set_window_rect(x=0, y=0, width=window_width, height=window_height)
    elif worker_id == 2:
        driver.set_window_rect(x=800, y=0, width=window_width, height=window_height)
    elif worker_id == 3:
        driver.set_window_rect(x=0, y=600, width=window_width, height=window_height)
    else:
        driver.set_window_rect(x=100*worker_id, y=100*worker_id, width=window_width, height=window_height)
        
    return driver


def wait_for_cloudflare(driver, timeout=30, prefix=""):
    start_time = time.time()
    actions = ActionChains(driver)
    clicked_cf = False
    
    while time.time() - start_time < timeout:
        cf_inputs = driver.find_elements(By.NAME, "cf-turnstile-response")
        
        if not cf_inputs:
            return True

        all_passed = True
        for cf_input in cf_inputs:
            if not cf_input.get_attribute("value"):
                all_passed = False
                break
        
        if all_passed:
            print(f"    {prefix}✅ Cloudflare 驗證已成功通過！")
            time.sleep(1) 
            return True
            
        try:
            cf_widgets = driver.find_elements(By.CLASS_NAME, "cf-turnstile")
            if cf_widgets and cf_widgets[0].is_displayed():
                widget = cf_widgets[0]
                
                if (time.time() - start_time > 1) and not clicked_cf:
                    print(f"    {prefix}⚠️ CF 尚未自動通過，嘗試手動點擊「驗證您是人類」...")
                    width = widget.size.get('width', 300)
                    if width == 0: width = 300
                    target_x = -(width / 2) + 30
                    try:
                        actions.move_to_element_with_offset(widget, target_x, 0).pause(0.5).click().perform()
                    except:
                        actions.move_to_element(widget).click().perform()
                    clicked_cf = True
                    time.sleep(0.5) 
                else:
                    x_offset = random.randint(-15, 15)
                    y_offset = random.randint(-5, 5)
                    actions.move_to_element_with_offset(widget, x_offset, y_offset).perform()
        except:
            pass 
            
        time.sleep(1)
        
    raise Exception("等待超時：Cloudflare 驗證未通過 (請觀察該視窗畫面是否有異常)")


def scrape_single_account(driver, account, worker_id=""):
    prefix = f"[執行緒-{worker_id}] " if worker_id else ""
    result = {"電號": str(account['電號']), "用戶戶名": account['用戶戶名'], "公司名稱": account['公司名稱']}
    wait = WebDriverWait(driver, 15) 
    
    try:
        driver.get("https://service.taipower.com.tw/ebpps2/simplebill/simple-query-bill")
        
        ele_number_input = wait.until(EC.element_to_be_clickable((By.ID, "custNo")))
        print(f"    {prefix}準備查詢電號: {result['電號']}...")
        ele_number_input.click() 
        ele_number_input.clear()
        ele_number_input.send_keys(result['電號'])
        
        print(f"    {prefix}等待 CF 驗證...")
        wait_for_cloudflare(driver, prefix=prefix)
        
        submit_btn = driver.find_element(By.XPATH, "//input[@type='submit' and @value='查詢']")
        driver.execute_script("arguments[0].click();", submit_btn)
        
        print(f"    {prefix}等待結果載入並尋找【查看帳單明細】按鈕...")
        time.sleep(1)  
        
        orange_btn = wait.until(EC.element_to_be_clickable((By.ID, "showBillQueryDetail")))
        time.sleep(1) 
        
        actions = ActionChains(driver)
        actions.move_to_element(orange_btn).pause(random.uniform(0.3, 0.7)).click().perform()
        
        print(f"    {prefix}準備輸入用戶戶名: {result['用戶戶名']}...")
        time.sleep(1)  
        
        name_input = wait.until(EC.visibility_of_element_located((By.ID, "billName")))
        time.sleep(0.5)
        
        x_offset = random.randint(-40, 40)
        y_offset = random.randint(-15, 15)
        actions.move_to_element_with_offset(name_input, x_offset, y_offset).pause(random.uniform(0.2, 0.5)).perform()
        
        actions.move_to_element(name_input).click().perform()
        name_input.clear()
        name_input.send_keys(result['用戶戶名'])
        time.sleep(1)
        
        print(f"    {prefix}等待 CF 驗證...")
        wait_for_cloudflare(driver, prefix=prefix)
        
        detail_btn = driver.find_element(By.XPATH, "//input[@name='Search' and @value='查詢明細']")
        actions.move_to_element(detail_btn).pause(random.uniform(0.3, 0.6)).click().perform()
        
        print(f"    {prefix}成功進入資料頁面，準備擷取用電數據...")
        wait.until(EC.presence_of_element_located((By.ID, "chartKWHdiv")))
        
        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(@aria-label, '用電')]")))
        except TimeoutException:
            pass 
            
        time.sleep(2) 
        
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        billing_period = ""
        th_tags = soup.find_all("th")
        for th in th_tags:
            if "計費期間" in th.text:
                td = th.find_next_sibling("td")
                if td:
                    billing_period = td.text.replace("\n", "").strip()
                break
        result["計費期間"] = billing_period

        year_dict = {}
        parts = re.split(r'id=["\']chartamtdiv["\']', page_source, flags=re.IGNORECASE)
        kwh_section = parts[0] if len(parts) > 1 else page_source
        
        aria_labels = re.findall(r'aria-label="([^"]+)"', kwh_section)
        
        for label in aria_labels:
            parts = label.split()
            if len(parts) >= 3:
                data_type = parts[0]  
                ym_text = parts[1]    
                usage_text = parts[2].replace(",", "") 
                
                if ym_text.isdigit() and usage_text.replace(".", "").isdigit():
                    base_year = int(ym_text[:3]) 
                    if "近期用電" in data_type:
                        year_dict.setdefault(base_year, []).append({"年月": ym_text, "用電": usage_text})
                    elif "去年用電" in data_type:
                        last_year = base_year - 1
                        last_ym_text = f"{last_year:03d}{ym_text[3:]}"
                        year_dict.setdefault(last_year, []).append({"年月": last_ym_text, "用電": usage_text})
                        
        if not year_dict:
            raise Exception("無法從網頁圖表中解析出用電數據，可能是該戶暫無歷史資料或圖表未渲染完成")
            
        result["公司年份資料"] = year_dict
        result["備註"] = "爬取成功"
        return result

    except Exception as e:
        try:
            alert = driver.switch_to.alert
            error_msg = alert.text
            alert.accept() 
            result["備註"] = f"處理失敗: 網頁提示 ({error_msg})"
            return result
        except NoAlertPresentException:
            pass 
            
        result["備註"] = f"處理失敗: {str(e)[:100]}" 
        return result


def worker_task(worker_id, chunk_df, total_accounts):
    stagger_delay = (worker_id - 1) * 12 + random.uniform(2, 5)
    print(f"啟動 [執行緒-{worker_id}]：分配到 {len(chunk_df)} 筆資料，將於 {stagger_delay:.1f} 秒後啟動瀏覽器...")
    time.sleep(stagger_delay)
    
    driver = init_driver(worker_id)
    worker_results = []
    
    try:
        for idx, (_, account) in enumerate(chunk_df.iterrows()):
            print(f"\n[執行緒-{worker_id}] 處理中 ({idx+1}/{len(chunk_df)}): {account['公司名稱']} ({account['電號']})")
            
            for attempt in range(1, MAX_RETRIES + 1):
                result = scrape_single_account(driver, account, worker_id)
                
                if "處理失敗" not in result.get("備註", ""):
                    worker_results.append(result)
                    break 
                else:
                    if "網頁提示" in result.get("備註", ""):
                        print(f"  -> [執行緒-{worker_id}] 偵測到網頁警告，跳過此店家。")
                        worker_results.append(result)
                        break
                        
                    if attempt < MAX_RETRIES:
                        print(f"  -> [執行緒-{worker_id}] 嘗試第 {attempt} 次失敗 ({result.get('備註', '')})，準備重試...")
                        time.sleep(random.uniform(3, 6))
                    else:
                        print(f"  -> [執行緒-{worker_id}] 已達最大重試次數，跳過此店家。")
                        worker_results.append(result)
            
            time.sleep(random.uniform(2, 5))
            
    finally:
        try:
            driver.quit()
        except OSError:
            pass
        except Exception:
            pass
        print(f"\n✅ [執行緒-{worker_id}] 任務完成，瀏覽器已關閉。")
        
    return worker_results


def process_and_format_data(results):
    final_data_rows = []
    all_years = set(y for r in results for y in r.get("公司年份資料", {}).keys())
    if not all_years: return pd.DataFrame()
    year_range = sorted(list(all_years))

    for result in results:
        store_info = {"店名": result.get("公司名稱"), "用戶戶名": result.get("用戶戶名"), "電號": str(result.get("電號"))}
        if not result.get("公司年份資料"): continue

        year_dict = result["公司年份資料"]
        processed_data = {}
        
        for year in year_range:
            monthly_data = [None] * 12
            if year in year_dict:
                for record in year_dict[year]:
                    try:
                        ym_str = record["年月"]
                        if len(ym_str) >= 5:
                            month_idx = int(ym_str[3:5]) - 1
                            if 0 <= month_idx <= 11:
                                monthly_data[month_idx] = float(record["用電"]) 
                    except (ValueError, IndexError, TypeError): 
                        continue
            processed_data[year] = monthly_data

        for year in year_range:
            monthly_data = processed_data[year]
            for i in range(0, 12, 2):
                m1, m2 = monthly_data[i], monthly_data[i+1]
                if m1 is not None and m2 is None:
                    avg = m1 / 2.0
                    monthly_data[i], monthly_data[i+1] = avg, avg
                elif m1 is None and m2 is not None:
                    avg = m2 / 2.0
                    monthly_data[i], monthly_data[i+1] = avg, avg
        
        for year in year_range:
            for month_idx in range(12):
                usage = processed_data[year][month_idx]
                if usage is not None:
                    new_row = store_info.copy()
                    new_row["年份"] = year
                    new_row["月份"] = f"{month_idx + 1}月"
                    new_row["用電量(度)"] = usage
                    new_row["最新計費期間"] = result.get("計費期間", "")
                    final_data_rows.append(new_row)

    if not final_data_rows: return pd.DataFrame()
    
    base_cols = ["店名", "用戶戶名", "電號", "最新計費期間", "年份", "月份", "用電量(度)"]
    df = pd.DataFrame(final_data_rows)
    for col in base_cols:
        if col not in df.columns: df[col] = ""
            
    return df[base_cols]

# ==========================================
# 💡 新增：儲存至 PostgreSQL 資料庫模組
# ==========================================
def save_to_database(df):
    if df.empty:
        return

    print(f"\n🐳 系統：準備將 {len(df)} 筆帳單數據寫入 PostgreSQL 資料庫...")
    
    # 建表語法 (自癒機制：若資料表不存在則自動建立，保護既有 pgdata)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS taipower_billing_records (
        id SERIAL PRIMARY KEY,
        store_name VARCHAR(255) NOT NULL,
        account_name VARCHAR(255),
        account_number VARCHAR(100) NOT NULL,
        billing_period VARCHAR(100),
        billing_year INTEGER NOT NULL,
        billing_month VARCHAR(20) NOT NULL,
        usage_degree NUMERIC(15, 4),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT unique_taipower_record UNIQUE (store_name, account_number, billing_year, billing_month)
    );
    """
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cursor = conn.cursor()
        
        # 1. 確保資料表存在
        cursor.execute(create_table_query)
        
        # 2. 準備寫入的資料
        records_to_insert = []
        for _, row in df.iterrows():
            usage_val = float(row['用電量(度)']) if pd.notnull(row['用電量(度)']) else 0
            records_to_insert.append((
                row['店名'], row['用戶戶名'], str(row['電號']),
                row['最新計費期間'], int(row['年份']), str(row['月份']), usage_val
            ))

        # 3. 執行批次寫入 (UPSERT: 如果已經抓過同一個月的，就更新用電量與計費期間)
        insert_query = """
            INSERT INTO taipower_billing_records (
                store_name, account_name, account_number, billing_period,
                billing_year, billing_month, usage_degree
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (store_name, account_number, billing_year, billing_month)
            DO UPDATE SET
                usage_degree = EXCLUDED.usage_degree,
                billing_period = EXCLUDED.billing_period,
                created_at = CURRENT_TIMESTAMP;
        """
        execute_batch(cursor, insert_query, records_to_insert)
        conn.commit()
        print(f"    ✅ 資料庫寫入成功：已新增或更新 {len(records_to_insert)} 筆資料表 [taipower_billing_records]！")

    except Exception as e:
        print(f"    ❌ 資料庫寫入失敗，請確認資料庫已開啟且連線正常: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

# ==========================================
# 💡 新增：儲存「失敗紀錄」至 PostgreSQL 資料庫模組
# ==========================================
def save_errors_to_database(df):
    if df.empty:
        return

    print(f"\n🐳 系統：準備將 {len(df)} 筆【失敗紀錄】寫入 PostgreSQL 資料庫...")
    
    # 建立錯誤日誌表 (每次寫入只做紀錄，不覆蓋，當作歷程追蹤)
    create_table_query = """
    CREATE TABLE IF NOT EXISTS taipower_scraping_errors (
        id SERIAL PRIMARY KEY,
        store_name VARCHAR(255),
        account_name VARCHAR(255),
        account_number VARCHAR(100),
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        cursor = conn.cursor()
        
        # 1. 確保錯誤資料表存在
        cursor.execute(create_table_query)
        
        # 2. 準備寫入的資料
        records_to_insert = []
        for _, row in df.iterrows():
            records_to_insert.append((
                row.get('店名', ''), row.get('用戶戶名', ''), str(row.get('電號', '')), row.get('備註', '')
            ))

        # 3. 執行批次寫入 (單純紀錄日誌)
        insert_query = """
            INSERT INTO taipower_scraping_errors (
                store_name, account_name, account_number, error_message
            ) VALUES (%s, %s, %s, %s);
        """
        execute_batch(cursor, insert_query, records_to_insert)
        conn.commit()
        print(f"    ✅ 資料庫寫入成功：已記錄 {len(records_to_insert)} 筆失敗資訊至 [taipower_scraping_errors]！")

    except Exception as e:
        print(f"    ❌ 失敗紀錄寫入資料庫失敗: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()


# --- 主執行區 ---
if __name__ == "__main__":
    if len(sys.argv) >= 2:
        max_browsers = int(sys.argv[1])
    else:
        user_input = input(f"請輸入同時執行的瀏覽器數量 [預設: {DEFAULT_MAX_BROWSERS}]: ").strip()
        max_browsers = int(user_input) if user_input.isdigit() else DEFAULT_MAX_BROWSERS

    try:
        import undetected_chromedriver
    except ImportError:
        print("錯誤：尚未安裝 undetected-chromedriver。")
        exit()

    try:
        df_accounts = pd.read_csv(ACCOUNTS_CSV_PATH, encoding='utf-8', dtype=str)
        total_accounts = len(df_accounts)
        print(f"成功讀取 {total_accounts} 筆店家資料。")
    except FileNotFoundError:
        print(f"錯誤：找不到帳號檔案 {ACCOUNTS_CSV_PATH}")
        exit()
    except Exception as e:
        print(f"錯誤：讀取 CSV 檔案時發生問題 - {e}")
        exit()
    
    REQUIRED_COLUMNS = ['電號', '用戶戶名', '公司名稱']
    if not all(col in df_accounts.columns for col in REQUIRED_COLUMNS):
        print(f"錯誤：CSV 檔案缺少必要欄位: {', '.join(REQUIRED_COLUMNS)}")
        exit()

    all_results = []
    
    actual_workers = min(max_browsers, total_accounts)
    chunk_size = math.ceil(total_accounts / actual_workers) if actual_workers > 0 else 1
    chunks = [df_accounts.iloc[i:i + chunk_size] for i in range(0, total_accounts, chunk_size)]
    
    print(f"\n🚀 開始啟動多執行緒爬蟲：將開啟 {actual_workers} 個瀏覽器同時作業...")
    
    with ThreadPoolExecutor(max_workers=actual_workers) as executor:
        futures = [executor.submit(worker_task, i+1, chunks[i], total_accounts) for i in range(actual_workers)]
        
        for future in as_completed(futures):
            try:
                thread_results = future.result()
                all_results.extend(thread_results)
            except Exception as e:
                print(f"❌ 某個執行緒發生崩潰: {e}")

    print("\n--- 🏁 所有執行緒皆已完成，準備寫入檔案與資料庫 ---")

    successful_results = [r for r in all_results if r.get("公司年份資料")]
    error_results = [r for r in all_results if not r.get("公司年份資料")]
    
    df_final_data = process_and_format_data(successful_results)
    df_final_errors = pd.DataFrame([{"店名": r.get("公司名稱"), "用戶戶名": r.get("用戶戶名"), "電號": r.get("電號"), "備註": r.get("備註")} for r in error_results])

    # 💡 新增：若有爬到成功的資料，同步寫入資料庫
    if not df_final_data.empty:
        save_to_database(df_final_data)

    # 💡 新增：將失敗的紀錄也獨立寫入資料庫的錯誤日誌表
    if not df_final_errors.empty:
        save_errors_to_database(df_final_errors)

    # 匯出至 Excel 檔案
    if not df_final_data.empty or not df_final_errors.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        new_filename = f"爬取結果_{timestamp}.xlsx"
        new_output_path = os.path.join(OUTPUT_FOLDER_PATH, new_filename)
        
        print(f"\n正在將本次爬取結果寫入 Excel 檔案: {new_output_path}")
        try:
            os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
            with pd.ExcelWriter(new_output_path, engine="openpyxl") as writer:
                if not df_final_data.empty:
                    df_final_data.to_excel(writer, index=False, sheet_name="台電歷年電費")
                if not df_final_errors.empty:
                    df_final_errors[['店名', '用戶戶名', '電號', '備註']].to_excel(writer, index=False, sheet_name="爬取失敗名單")
            print(f"✅ 成功建立 Excel 檔案: {new_output_path}")
        except Exception as e:
            print(f"❌ 錯誤：儲存 Excel 檔案失敗 - {e}")
    else:
        print("沒有任何新資料可供寫入，程序結束。")