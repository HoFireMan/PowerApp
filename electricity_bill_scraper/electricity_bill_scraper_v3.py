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

# --- 配置區 ---
# 💡 動態獲取當前腳本所在的資料夾路徑 (完美相容 GUI 系統的呼叫)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# CSV 檔案路徑與輸出路徑改為動態拼裝
ACCOUNTS_CSV_PATH = os.path.join(BASE_DIR, 'accounts.csv')
OUTPUT_FOLDER_PATH = os.path.join(BASE_DIR, 'output')

# 💡 多執行緒與重試設定
DEFAULT_MAX_BROWSERS = 3     # 預設同時運作的瀏覽器數量
MAX_RETRIES = 3              # 單一帳戶最高重試次數


# --- 核心邏輯區 ---

def get_chrome_major_version():
    """💡 自動從 Windows 登錄檔獲取當前安裝的 Chrome 主版本號"""
    try:
        import winreg
        # Chrome 的版本號通常儲存在這個登錄檔路徑中
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon")
        version_str, _ = winreg.QueryValueEx(key, "version")
        # 取得主版本號 (例如 "149.0.7827.103" 會被截斷成 149)
        major_version = int(version_str.split('.')[0])
        return major_version
    except Exception:
        return None

def init_driver(worker_id):
    """初始化 undetected-chromedriver，並根據 worker_id 排列視窗位置"""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument('--disable-popup-blocking')
    
    # 關閉 Chrome 背景節能與降速機制
    options.add_argument('--disable-background-timer-throttling')
    options.add_argument('--disable-backgrounding-occluded-windows')
    options.add_argument('--disable-renderer-backgrounding')
    
    # 💡 終極解法：自動獲取當前電腦的 Chrome 版本，避免更新導致的 session 崩潰
    chrome_version = get_chrome_major_version()
    if chrome_version:
        driver = uc.Chrome(options=options, version_main=chrome_version)
    else:
        # 如果無法讀取登錄檔，就放手讓 uc 套件自己去猜
        driver = uc.Chrome(options=options)
    
    # 💡 智慧視窗排列邏輯 (設定每個視窗寬800、高600，避免互相遮擋)
    window_width = 800
    window_height = 600
    
    if worker_id == 1:
        driver.set_window_rect(x=0, y=0, width=window_width, height=window_height)        # 左上角
    elif worker_id == 2:
        driver.set_window_rect(x=800, y=0, width=window_width, height=window_height)      # 右上角
    elif worker_id == 3:
        driver.set_window_rect(x=0, y=600, width=window_width, height=window_height)      # 左下角
    else:
        # 如果超過3個視窗，就稍微重疊排列
        driver.set_window_rect(x=100*worker_id, y=100*worker_id, width=window_width, height=window_height)
        
    return driver


def wait_for_cloudflare(driver, timeout=30, prefix=""):
    """
    嚴格等待 Cloudflare 驗證通過 (智能點擊優化版)：
    不強制點擊，而是針對 CF 驗證框進行安全的滑鼠懸停與微動。
    若 3 秒後仍未自動通過，會精準計算出驗證框左側勾選方塊的位置並模擬點擊。
    """
    start_time = time.time()
    actions = ActionChains(driver)
    clicked_cf = False
    
    while time.time() - start_time < timeout:
        # 尋找頁面中所有的 Cloudflare 隱藏 input
        cf_inputs = driver.find_elements(By.NAME, "cf-turnstile-response")
        
        # 如果畫面上沒有 CF 組件，代表不需驗證直接放行
        if not cf_inputs:
            return True

        # 嚴格檢查：只要有任何一個 CF 還沒拿到 Token (value 為空)，就不算通過
        all_passed = True
        for cf_input in cf_inputs:
            if not cf_input.get_attribute("value"):
                all_passed = False
                break
        
        if all_passed:
            print(f"    {prefix}✅ Cloudflare 驗證已成功通過！")
            time.sleep(1) # 拿到 Token 後稍微停頓一秒，確保按鈕解除鎖定
            return True
            
        # 💡 軌跡模擬與智能點擊
        try:
            cf_widgets = driver.find_elements(By.CLASS_NAME, "cf-turnstile")
            if cf_widgets and cf_widgets[0].is_displayed():
                widget = cf_widgets[0]
                
                # 如果等待超過 3 秒還沒拿到 token，且還未點擊過，代表 CF 需要手動勾選
                if (time.time() - start_time > 1) and not clicked_cf:
                    print(f"    {prefix}⚠️ CF 尚未自動通過，嘗試手動點擊「驗證您是人類」...")
                    
                    # 取得元素大小，計算勾選框的相對位置 (勾選框通常在最左邊)
                    width = widget.size.get('width', 300)
                    if width == 0: width = 300
                    
                    # ActionChains offset 是從元素中心點起算
                    # 往左移 (width / 2)，再加上 30 像素回到勾選方塊的位置
                    target_x = -(width / 2) + 30
                    
                    try:
                        actions.move_to_element_with_offset(widget, target_x, 0).pause(0.5).click().perform()
                    except:
                        # 備用方案：如果偏移發生異常，直接點擊中心點
                        actions.move_to_element(widget).click().perform()
                        
                    clicked_cf = True
                    time.sleep(0.5) # 點擊後多等一下讓它轉圈
                else:
                    # 尚未達點擊時間或已點擊，就在原地輕微抖動
                    x_offset = random.randint(-15, 15)
                    y_offset = random.randint(-5, 5)
                    actions.move_to_element_with_offset(widget, x_offset, y_offset).perform()
        except:
            pass 
            
        time.sleep(1)
        
    raise Exception("等待超時：Cloudflare 驗證未通過 (請觀察該視窗畫面是否有異常)")


def scrape_single_account(driver, account, worker_id=""):
    """依照台電最新版網頁流程爬取單一帳戶"""
    prefix = f"[執行緒-{worker_id}] " if worker_id else ""
    result = {"電號": str(account['電號']), "用戶戶名": account['用戶戶名'], "公司名稱": account['公司名稱']}
    wait = WebDriverWait(driver, 15) 
    
    try:
        # ==========================================
        # 步驟 1: 前往首頁並輸入電號
        # ==========================================
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
        
        # ==========================================
        # 步驟 2: 進入「繳費狀況查詢」，點擊查看明細
        # ==========================================
        print(f"    {prefix}等待結果載入並尋找【查看帳單明細】按鈕...")
        time.sleep(1)  # 強制等待 AJAX 請求與「載入中」動畫消失
        
        # 等待按鈕處於可互動狀態
        orange_btn = wait.until(EC.element_to_be_clickable((By.ID, "showBillQueryDetail")))
        
        time.sleep(1) 
        
        # 💡 擬真滑鼠：移動到按鈕上稍微停頓再點擊
        actions = ActionChains(driver)
        actions.move_to_element(orange_btn).pause(random.uniform(0.3, 0.7)).click().perform()
        
        # ==========================================
        # 步驟 3: 展開戶名輸入區，模擬滑鼠軌跡、等待 CF 驗證後一次性填入
        # ==========================================
        print(f"    {prefix}準備輸入用戶戶名: {result['用戶戶名']}...")
        time.sleep(1)  # 讓點擊後的表單與 CF 模組有時間展開渲染
        
        # 等待輸入框出現
        name_input = wait.until(EC.visibility_of_element_located((By.ID, "billName")))
        
        time.sleep(0.5)
        
        # 💡 擬真滑鼠軌跡：在輸入框周圍隨機游移 (注意這裡先加上 .perform() 執行滑鼠動作)
        x_offset = random.randint(-40, 40)
        y_offset = random.randint(-15, 15)
        actions.move_to_element_with_offset(name_input, x_offset, y_offset).pause(random.uniform(0.2, 0.5)).perform()
        
        # 💡 讓 Cloudflare 偵測到鍵盤與點擊行為，可大幅降低卡在勾選框的機率
        actions.move_to_element(name_input).click().perform()
        name_input.clear()
        name_input.send_keys(result['用戶戶名'])
        time.sleep(1)
        
        # 填寫完畢後，等待/處理 Cloudflare 驗證
        print(f"    {prefix}等待 CF 驗證...")
        wait_for_cloudflare(driver, prefix=prefix)
        
        # 定位查詢明細按鈕
        detail_btn = driver.find_element(By.XPATH, "//input[@name='Search' and @value='查詢明細']")
        
        # 擬真滑鼠移動過去點擊
        actions.move_to_element(detail_btn).pause(random.uniform(0.3, 0.6)).click().perform()
        
        # ==========================================
        # 步驟 4: 進入結果頁面，解析動態圖表數據
        # ==========================================
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
    """單一執行緒的工作任務"""
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
    """將爬取結果整理成標準的 長表格 (Tidy Data) 格式"""
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


# --- 主執行區 ---
if __name__ == "__main__":
    # 💡 接收從 main_gui.py 傳來的參數 (瀏覽器數量)
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

    print("\n--- 🏁 所有執行緒皆已完成，準備寫入檔案 ---")

    successful_results = [r for r in all_results if r.get("公司年份資料")]
    error_results = [r for r in all_results if not r.get("公司年份資料")]
    
    df_final_data = process_and_format_data(successful_results)
    df_final_errors = pd.DataFrame([{"店名": r.get("公司名稱"), "用戶戶名": r.get("用戶戶名"), "電號": r.get("電號"), "備註": r.get("備註")} for r in error_results])

    if not df_final_data.empty or not df_final_errors.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        new_filename = f"爬取結果_{timestamp}.xlsx"
        new_output_path = os.path.join(OUTPUT_FOLDER_PATH, new_filename)
        
        print(f"正在將本次爬取結果寫入新檔案: {new_output_path}")
        try:
            os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
            with pd.ExcelWriter(new_output_path, engine="openpyxl") as writer:
                if not df_final_data.empty:
                    df_final_data.to_excel(writer, index=False, sheet_name="台電歷年電費")
                if not df_final_errors.empty:
                    df_final_errors[['店名', '用戶戶名', '電號', '備註']].to_excel(writer, index=False, sheet_name="爬取失敗名單")
            print(f"✅ 成功建立檔案: {new_output_path}")
        except Exception as e:
            print(f"❌ 錯誤：儲存 Excel 檔案失敗 - {e}")
    else:
        print("沒有任何新資料可供寫入，程序結束。")