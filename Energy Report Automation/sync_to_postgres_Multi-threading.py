import requests
import time
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from tqdm import tqdm
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import execute_batch
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# 💡 匯入 dotenv 套件
from dotenv import load_dotenv

# --- 1. 絕對路徑與環境變數設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
ENV_PATH = os.path.join(ROOT_DIR, ".env")

load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "energy_reports")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "admin_password")

API_URL = os.getenv("API_URL")

EXCEL_FILE_PATH = os.path.join(CURRENT_DIR, "店家ID.xlsx")
EXCEL_SHEET_NAME = "店家資訊"
EXCEL_COLUMN_NAME = "ID"

DEFAULT_START_TOTAL = "2020-05-20"  
DEFAULT_END_TOTAL = "2026-06-01"    
DEFAULT_STEP_DAYS = 60              
DEFAULT_MAX_WORKERS = 10

HEADERS = {"Content-Type": "application/json"}

FURNITURE_KEYWORDS = [
    '電燈', '冰箱', '冷氣', '冷凍櫃', '微波爐', '烤箱', 
    '電鍋', '氣炸鍋', '洗碗機', '咖啡機', '飲水機', '電風扇', '總電源',
    '除濕機', '空氣清淨機', '洗衣機', '烘衣機', '電視', '投影機',
    '插座', '電腦', '伺服器', '監視器', '吹風機', '熱水器', '抽風機'
]

# 💡 效能優化：為每個執行緒建立專屬的連線池 (Keep-Alive)
thread_local = threading.local()

def get_session():
    """獲取當前執行緒專屬的 requests Session，保持 TCP 連線不中斷"""
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        # 掛載 adapter 來增加連線池大小與重試機制，進一步提升穩定性
        adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=3)
        thread_local.session.mount('http://', adapter)
        thread_local.session.mount('https://', adapter)
    return thread_local.session


# --- 2. 輔助函式 ---
def get_date_segments(start_str, end_str, step):
    start_str = start_str.split(' ')[0]
    end_str = end_str.split(' ')[0]
    
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    segments = []
    curr = start
    while curr < end:
        seg_end = min(curr + timedelta(days=step), end)
        segments.append({
            "start": curr.strftime("%Y-%m-%d 00:00"),
            "end": seg_end.strftime("%Y-%m-%d 00:00")
        })
        curr = seg_end
    return segments

def extract_device_code(device_name):
    name_str = str(device_name)
    match = re.search(r'[A-Za-z0-9]+', name_str)
    return match.group() if match else ""

def extract_furniture_type(row):
    device_name = str(row.get('devicename', ''))
    type_name = str(row.get('devicetypename', ''))
    for keyword in FURNITURE_KEYWORDS:
        if keyword in device_name: return keyword
    if "其他" in type_name:
        parts = device_name.split(' ', 1)
        if len(parts) > 1: return parts[1]
        return device_name
    return type_name

def process_and_insert_data(conn, raw_data, branch_code):
    if not raw_data: return 0
    df = pd.DataFrame(raw_data)
    df = df.dropna(subset=['devicename'])
    df = df[df['devicename'].astype(str).str.strip() != ""]
    if df.empty: return 0

    df['reportdate'] = pd.to_datetime(df['reportdate']).dt.strftime('%Y-%m-%d')
    df['device_code_new'] = df['devicename'].apply(extract_device_code)
    df['device_type_2_new'] = df.apply(extract_furniture_type, axis=1)

    records_to_insert = []
    for _, row in df.iterrows():
        records_to_insert.append((
            row.get('branchname', branch_code), row['devicename'], row.get('devicetypename', ''),
            row['reportdate'], row['starttm'], row['endtm'], row.get('degree', 0),
            row['device_code_new'], row['device_type_2_new']
        ))

    insert_query = """
        INSERT INTO power_consumption_records (
            branch_name, device_name, device_type, report_date, 
            start_time, end_time, degree, device_code_new, device_type_2_new
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (branch_name, device_name, report_date, start_time) 
        DO NOTHING;
    """
    
    cursor = conn.cursor()
    try:
        execute_batch(cursor, insert_query, records_to_insert)
        conn.commit()
        return len(records_to_insert)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()

# --- 3. 核心任務函數 ---
def fetch_and_store_task(branch_code, start_str, end_str, current_step, db_pool):
    payload = {
        "header": {
            "datetime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
            "txcode": "BASIC_REPORT_CREATE",
            "appversion": "2023082401",
            "usercode": "antnex",
            "token": ""
        },
        "message": {
            "startdate": start_str, "enddate": end_str,
            "branchcode": branch_code, "devicecodelist": []
        }
    }

    try:
        if not API_URL:
            raise Exception("尚未設定 API_URL 環境變數，請確認 .env 檔案是否存在且格式正確。")
            
        # 💡 效能優化：使用專屬的 Session 隧道發送請求，省去每次重新 SSL 握手的大量時間
        session = get_session()
        response = session.post(API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        json_data = response.json()
        
        processed_count = 0
        if json_data and 'message' in json_data and 'data' in json_data['message']:
            data_list = json_data['message']['data']
            if data_list:
                conn = db_pool.getconn()
                try: processed_count = process_and_insert_data(conn, data_list, branch_code)
                finally: db_pool.putconn(conn)
                    
        return {"status": "success", "branch": branch_code, "seg": f"{start_str}~{end_str}", "count": processed_count}

    except Exception as e:
        if current_step > 30:
            fallback_step = 30
            tqdm.write(f"  [重試] 店家 {branch_code} 時段 {start_str}~{end_str} 發生錯誤，將拆分為 {fallback_step} 天重試...")
        elif current_step > 7:
            fallback_step = 7
            tqdm.write(f"  [重試] 店家 {branch_code} 時段 {start_str}~{end_str} 發生錯誤，將拆分為 {fallback_step} 天重試...")
        else:
            return {"status": "error", "branch": branch_code, "seg": f"{start_str}~{end_str}", "error": str(e), "count": 0}

        sub_segments = get_date_segments(start_str, end_str, fallback_step)
        total_fallback_count = 0
        
        for sub_seg in sub_segments:
            res = fetch_and_store_task(branch_code, sub_seg['start'], sub_seg['end'], fallback_step, db_pool)
            if res['status'] == 'success': total_fallback_count += res['count']
            else: tqdm.write(f"  [錯誤] 店家 {branch_code} 子時段 {res['seg']} 最終失敗: {res['error']}")

        return {"status": "success", "branch": branch_code, "seg": f"{start_str}~{end_str} (降級重試完成)", "count": total_fallback_count}

# --- 4. 主程式 ---
if __name__ == '__main__':
    if len(sys.argv) >= 5: 
        start_total = sys.argv[1]
        end_total = sys.argv[2]
        step_days = int(sys.argv[3])
        max_workers = int(sys.argv[4])
    else:
        user_start = input(f"請輸入起始日期 [預設: {DEFAULT_START_TOTAL}]: ").strip()
        start_total = user_start if user_start else DEFAULT_START_TOTAL
        
        user_end = input(f"請輸入結束日期 [預設: {DEFAULT_END_TOTAL}]: ").strip()
        end_total = user_end if user_end else DEFAULT_END_TOTAL
        
        user_step = input(f"請輸入間隔天數 [預設: {DEFAULT_STEP_DAYS}]: ").strip()
        step_days = int(user_step) if user_step.isdigit() else DEFAULT_STEP_DAYS
        
        user_workers = input(f"請輸入執行核心數 [預設: {DEFAULT_MAX_WORKERS}]: ").strip()
        max_workers = int(user_workers) if user_workers.isdigit() else DEFAULT_MAX_WORKERS

    start_time_exec = time.time()
    print(f"\n📅 準備擷取區間: {start_total} 至 {end_total}")
    print(f"⏳ 初始間隔天數: {step_days} 天")
    print(f"🚀 啟動多執行緒並發數 (MAX_WORKERS): {max_workers}\n")
    
    try:
        df_stores = pd.read_excel(EXCEL_FILE_PATH, sheet_name=EXCEL_SHEET_NAME, usecols=[EXCEL_COLUMN_NAME])
        store_codes = df_stores[EXCEL_COLUMN_NAME].dropna().astype(str).tolist()
    except Exception as e:
        sys.exit(f"讀取 Excel 失敗: {e}")

    db_pool = None
    try:
        db_pool = ThreadedConnectionPool(
            minconn=1, maxconn=max_workers,
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        print("✅ 成功建立 PostgreSQL 連線池！")
    except Exception as e:
        sys.exit(f"❌ 資料庫連線池建立失敗: {e}")

    date_segments = get_date_segments(start_total, end_total, step_days)
    tasks = [(branch, seg) for branch in store_codes for seg in date_segments]
    
    print(f"預計處理 {len(store_codes)} 個店家，初始產生 {len(tasks)} 個 API 請求任務。")

    total_processed = 0

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(fetch_and_store_task, branch, seg['start'], seg['end'], step_days, db_pool): (branch, seg) 
                for branch, seg in tasks
            }
            
            for future in tqdm(as_completed(future_to_task), total=len(tasks), desc="總進度", file=sys.stdout, miniters=1, mininterval=0.1):
                result = future.result()
                if result['status'] == 'success':
                    total_processed += result['count']
                else:
                    tqdm.write(f"  [錯誤] 店家 {result['branch']} 時段 {result['seg']} : {result['error']}")
    finally:
        if db_pool:
            db_pool.closeall()
            print("資料庫連線池已安全關閉。")

    print("\n" + "="*30)
    print("🎉 擷取與寫入程序結束！")
    print(f"共嘗試處理 {total_processed} 筆資料。")
    print(f"總耗時: {time.time() - start_time_exec:.2f} 秒")
    print("="*30)