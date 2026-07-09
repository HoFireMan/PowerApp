import os
import sys
import time
import pandas as pd
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# --- 1. 初始化與環境設定 ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
ENV_PATH = os.path.join(ROOT_DIR, ".env")
load_dotenv(ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
if DB_HOST.lower() == "localhost": DB_HOST = "127.0.0.1"
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "energy_reports")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASS", "admin_password")

EXCEL_FILE_PATH = os.path.join(CURRENT_DIR, "店家ID.xlsx")
EXCEL_SHEET_NAME = "店家資訊"
EXCEL_COLUMN_NAME = "ID"

def main():
    if len(sys.argv) >= 3:
        start_date_str = sys.argv[1]
        end_date_str = sys.argv[2]
    else:
        start_date_str = input("請輸入起始日期 (YYYY-MM-DD): ").strip()
        end_date_str = input("請輸入結束日期 (YYYY-MM-DD): ").strip()

    print(f"=== 啟動感測器數據空缺檢測 ===")
    print(f"📅 檢測區間: {start_date_str} 至 {end_date_str}")

    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
        expected_days = (end_dt - start_dt).days + 1
        print(f"⏳ 該區間應有資料天數: {expected_days} 天\n")
    except Exception as e:
        sys.exit(f"❌ 日期格式解析錯誤: {e}")

    # 1. 讀取預期店家清單
    try:
        df_stores = pd.read_excel(EXCEL_FILE_PATH, sheet_name=EXCEL_SHEET_NAME, usecols=[EXCEL_COLUMN_NAME])
        expected_stores = set(df_stores[EXCEL_COLUMN_NAME].dropna().astype(str).tolist())
    except Exception as e:
        sys.exit(f"❌ 讀取 店家ID.xlsx 失敗: {e}")

    # 2. 連線資料庫
    try:
        conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASS)
        print("✅ 成功連線至資料庫，開始運算龐大數據...")
    except Exception as e:
        sys.exit(f"❌ 資料庫連線失敗: {e}")

    # 3. 執行檢測查詢
    try:
        query = """
            SELECT 
                branch_name, 
                device_name, 
                COUNT(DISTINCT report_date) as reported_days, 
                MAX(report_date) as last_report_date
            FROM power_consumption_records 
            WHERE report_date >= %s AND report_date <= %s
            GROUP BY branch_name, device_name
        """
        df_db = pd.read_sql(query, conn, params=(start_date_str, end_date_str))
        
        # 找出完全沒有資料的店家
        actual_stores = set(df_db['branch_name'].unique()) if not df_db.empty else set()
        missing_stores = list(expected_stores - actual_stores)
        
        df_gap_devices = pd.DataFrame()
        
        if not df_db.empty:
            df_db['應有天數'] = expected_days
            df_db['缺漏天數'] = expected_days - df_db['reported_days']
            df_gap_devices = df_db[df_db['缺漏天數'] > 0].copy()
            df_gap_devices = df_gap_devices.sort_values(by=['缺漏天數', 'branch_name'], ascending=[False, True])
            
            # 重新命名與排列欄位方便閱讀
            df_gap_devices = df_gap_devices.rename(columns={
                'branch_name': '店家ID',
                'device_name': '設備名稱',
                'reported_days': '實際有資料天數',
                'last_report_date': '最後收到資料日期'
            })
            df_gap_devices = df_gap_devices[['店家ID', '設備名稱', '應有天數', '實際有資料天數', '缺漏天數', '最後收到資料日期']]

    except Exception as e:
        sys.exit(f"❌ 資料庫查詢與運算失敗: {e}")
    finally:
        conn.close()

    # 4. 輸出 Excel 報告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"數據空缺檢測報告_{timestamp}.xlsx"
    report_path = os.path.join(CURRENT_DIR, report_filename)

    try:
        with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
            # Sheet 1: 設備資料斷層
            if not df_gap_devices.empty:
                df_gap_devices.to_excel(writer, sheet_name="設備資料斷層", index=False)
            else:
                pd.DataFrame({"訊息": ["該期間內所有上線設備資料皆完整，無斷層"]}).to_excel(writer, sheet_name="設備資料斷層", index=False)
            
            # Sheet 2: 完全無數據店家
            if missing_stores:
                df_missing = pd.DataFrame(missing_stores, columns=["完全無資料之店家ID"])
                df_missing.to_excel(writer, sheet_name="完全無數據店家", index=False)
            else:
                pd.DataFrame({"訊息": ["名單內所有店家在該期間皆有資料回傳"]}).to_excel(writer, sheet_name="完全無數據店家", index=False)

        print("\n" + "="*40)
        print("🎉 數據空缺檢測完成！")
        print(f"📊 發現 【{len(missing_stores)}】 家店完全無資料回傳。")
        print(f"📊 發現 【{len(df_gap_devices) if not df_gap_devices.empty else 0}】 個設備發生資料斷層/缺漏。")
        print(f"📁 詳細報告已匯出至: \n{report_path}")
        print("="*40)

    except Exception as e:
        print(f"❌ 產出 Excel 報告時發生錯誤: {e}")

if __name__ == "__main__":
    main()