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

from dotenv import load_dotenv

# --- 1. 絕對路徑與環境變數設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
ENV_PATH = os.path.join(ROOT_DIR, ".env")

load_dotenv(ENV_PATH)

# 💡 效能優化：徹底避開 IPv6 (::1) 造成的 DNS 尋址超時陷阱
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
if DB_HOST.lower() == "localhost":
    DB_HOST = "127.0.0.1"
    
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "energy_reports")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "admin_password")

API_URL = os.getenv("API_URL")

# 預設時間與區間設定
DEFAULT_START_TOTAL = "2020-05-20"  
DEFAULT_END_TOTAL = "2026-06-01"    
DEFAULT_STEP_DAYS = 30              
DEFAULT_MAX_WORKERS = 10  # 💡 新增：預設使用 10 個核心飛速處理

HEADERS = {"Content-Type": "application/json"}

FURNITURE_KEYWORDS = [
    '電燈', '冰箱', '冷氣', '冷凍櫃', '微波爐', '烤箱', 
    '電鍋', '氣炸鍋', '洗碗機', '咖啡機', '飲水機', '電風扇', '總電源',
    '除濕機', '空氣清淨機', '洗衣機', '烘衣機', '電視', '投影機',
    '插座', '電腦', '伺服器', '監視器', '吹風機', '熱水器', '抽風機'
]

# 💡 新增：Keep-Alive 快速通關隧道 (提升網路請求速度)
thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.trust_env = False 
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
        print(f"寫入資料庫時發生錯誤: {e}")
        return 0
    finally:
        cursor.close()

def save_api_execution_log(start_date, end_date, total_count, success_count, failed_list_str):
    print(f"\n🐳 系統：準備將本次【單一/選定店家補抓】日誌寫入資料庫...")
    create_table_query = """
    CREATE TABLE IF NOT EXISTS sensor_api_execution_logs (
        id SERIAL PRIMARY KEY,
        target_start_date VARCHAR(20),
        target_end_date VARCHAR(20),
        total_stores_attempted INTEGER,
        successful_stores_count INTEGER,
        failed_stores_list TEXT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        cursor = conn.cursor()
        cursor.execute(create_table_query)
        insert_query = """
            INSERT INTO sensor_api_execution_logs (
                target_start_date, target_end_date, total_stores_attempted, 
                successful_stores_count, failed_stores_list
            ) VALUES (%s, %s, %s, %s, %s);
        """
        cursor.execute(insert_query, (start_date, end_date, total_count, success_count, failed_list_str))
        conn.commit()
        print(f"    ✅ 執行紀錄寫入成功！")
    except Exception as e:
        print(f"    ❌ 執行紀錄寫入資料庫失敗: {e}")
    finally:
        if 'conn' in locals() and conn:
            cursor.close()
            conn.close()

# 💡 修正 BUG：參數順序必須與 executor.submit 呼叫時保持完全一致
def fetch_segment_with_fallback(branch_code, start_str, end_str, current_step, db_pool):
    """包含自動降級重試機制的核心抓取函式 (回傳 tuple: 處理筆數, 是否有發生致命錯誤)"""
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
            raise Exception("尚未設定 API_URL 環境變數")
            
        # 💡 使用高效的 Session 隧道取代 requests.post
        session = get_session()
        response = session.post(API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        json_data = response.json()
        
        processed_count = 0
        if json_data and 'message' in json_data and 'data' in json_data['message']:
            data_list = json_data['message']['data']
            if data_list:
                # 安全地從池子取得連線，用完馬上歸還
                conn = db_pool.getconn()
                try: processed_count = process_and_insert_data(conn, data_list, branch_code)
                finally: db_pool.putconn(conn)
            
        return processed_count, False

    except Exception as e:
        if current_step > 30:
            fallback_step = 30
            tqdm.write(f"  [重試] 店家 {branch_code} 時段 {start_str}~{end_str} 發生錯誤，將拆分為 {fallback_step} 天重試...")
        elif current_step > 7:
            fallback_step = 7
            tqdm.write(f"  [重試] 店家 {branch_code} 時段 {start_str}~{end_str} 發生錯誤，將拆分為 {fallback_step} 天重試...")
        else:
            tqdm.write(f"  [放棄] 店家 {branch_code} 時段 {start_str}~{end_str} 已達最小重試天數仍失敗: {e}")
            return 0, True # 回傳 True 代表發生無法修復的錯誤
            
        sub_segments = get_date_segments(start_str, end_str, fallback_step)
        total_fallback_processed = 0
        has_fatal_error = False
        
        for sub_seg in sub_segments:
            # 💡 遞迴重試時，參數順序也要跟著修正
            cnt, is_err = fetch_segment_with_fallback(branch_code, sub_seg['start'], sub_seg['end'], fallback_step, db_pool)
            total_fallback_processed += cnt
            if is_err: has_fatal_error = True
            
        return total_fallback_processed, has_fatal_error

# --- 3. 主程式 ---
if __name__ == '__main__':
    if len(sys.argv) >= 5: 
        start_total = sys.argv[1]
        end_total = sys.argv[2]
        step_days = int(sys.argv[3])
        target_branch_arg = sys.argv[4]
    else:
        target_branch_arg = input("請輸入目標店家 ID (多個請用逗號分隔): ").strip()
        user_start = input(f"請輸入起始日期 (YYYY-MM-DD) [預設: {DEFAULT_START_TOTAL}]: ").strip()
        start_total = user_start if user_start else DEFAULT_START_TOTAL
        user_end = input(f"請輸入結束日期 (YYYY-MM-DD) [預設: {DEFAULT_END_TOTAL}]: ").strip()
        end_total = user_end if user_end else DEFAULT_END_TOTAL
        user_step = input(f"請輸入每次擷取天數 [預設: {DEFAULT_STEP_DAYS}]: ").strip()
        step_days = int(user_step) if user_step.isdigit() else DEFAULT_STEP_DAYS

    target_branches = [b.strip() for b in target_branch_arg.split(',') if b.strip()]

    start_time_exec = time.time()
    print(f"=== 啟動指定多店家併發補抓模式 ===")
    print(f"🎯 目標店家 ID: {', '.join(target_branches)}")
    print(f"📅 擷取區間: {start_total} 至 {end_total}")
    print(f"⏳ 間隔天數: {step_days} 天\n")

    # 💡 重大變更：升級為 ThreadedConnectionPool
    db_pool = None
    try:
        db_pool = ThreadedConnectionPool(
            minconn=1, maxconn=DEFAULT_MAX_WORKERS,
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS
        )
        print("✅ 成功建立 PostgreSQL 併發連線池！")
    except Exception as e:
        sys.exit(f"❌ 資料庫連線池建立失敗: {e}")

    date_segments = get_date_segments(start_total, end_total, step_days)
    
    # 💡 任務攤平魔法：把所有 店家 x 時間段 組合成任務清單
    tasks = [(branch, seg) for branch in target_branches for seg in date_segments]
    print(f"總共為 {len(target_branches)} 家店切分出 {len(tasks)} 個抓取任務。")

    total_processed = 0
    failed_branches = set()

    try:
        # 💡 使用 ThreadPoolExecutor 進行 10 核心飛速併發處理！
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as executor:
            future_to_task = {
                executor.submit(fetch_segment_with_fallback, branch, seg['start'], seg['end'], step_days, db_pool): (branch, seg) 
                for branch, seg in tasks
            }
            
            # 💡 desc 統一為 "總進度"，這會觸發 GUI 把畫面鎖死在同一行！不會再洗頻了
            for future in tqdm(as_completed(future_to_task), total=len(tasks), desc="總進度", file=sys.stdout, miniters=1, mininterval=0.1):
                processed_count, is_err = future.result()
                branch = future_to_task[future][0] # 從 mapping 抓出這個任務是哪個店家的
                
                total_processed += processed_count
                if is_err: 
                    failed_branches.add(branch)
    finally:
        if db_pool:
            db_pool.closeall()
            print("資料庫連線池已安全關閉。")

    # 結算與寫入日誌
    total_stores = len(target_branches)
    failed_count = len(failed_branches)
    success_count = total_stores - failed_count
    failed_list_str = ", ".join(list(failed_branches)) if failed_branches else "無"

    save_api_execution_log(start_total, end_total, total_stores, success_count, failed_list_str)

    print("\n" + "="*30)
    print("🎉 擷取與寫入程序結束！")
    print(f"共嘗試寫入 {total_processed} 筆資料。")
    print(f"成功店家: {success_count} 家 | 失敗店家: {failed_count} 家")
    print(f"總耗時: {time.time() - start_time_exec:.2f} 秒")
    print("="*30)