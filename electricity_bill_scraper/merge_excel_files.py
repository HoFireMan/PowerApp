import pandas as pd
import os
from datetime import datetime

# --- 配置區 ---
# 基準檔案與輸出檔案的所在資料夾
MERGE_FOLDER_PATH = r'C:\Users\admin\Code\Save Power\electricity_bill_scraper\merge'

# 新檔案 (爬取結果) 所在資料夾
NEW_FILES_FOLDER_PATH = r'C:\Users\admin\Code\Save Power\electricity_bill_scraper\output'


def find_sheets(sheets_dict):
    """取得資料與錯誤工作表"""
    data_sheet, error_sheet = pd.DataFrame(), pd.DataFrame()
    if not sheets_dict: return data_sheet, error_sheet
    
    if '台電歷年電費' in sheets_dict:
        data_sheet = sheets_dict['台電歷年電費']
    
    if '爬取失敗名單' in sheets_dict:
        error_sheet = sheets_dict['爬取失敗名單']
                
    return data_sheet, error_sheet


def merge_tidy_data(base_df, new_df):
    """極速合併邏輯：透過 Pandas 垂直合併後移除重複項目 (保留最新)"""
    if new_df.empty: return base_df
    if base_df.empty: return new_df
    
    print("    [系統] 正在執行標準資料合併 (保留最新數據)...")
    
    # 確保型態統一
    for df in [base_df, new_df]:
        df['電號'] = df['電號'].astype(str).str.replace(".0", "", regex=False)
        df['年份'] = df['年份'].astype(str)
        df['月份'] = df['月份'].astype(str)
    
    # 💡 極簡合併：把新資料疊在舊資料下方，然後對 [電號, 年份, 月份] 進行去重，保留最後一筆(也就是新的)
    combined_df = pd.concat([base_df, new_df], ignore_index=True)
    result_df = combined_df.drop_duplicates(subset=['電號', '年份', '月份'], keep='last')
    
    # 將相同電號最新爬到的「計費期間」回填給該電號的所有歷史紀錄，保持畫面整潔
    latest_periods = new_df[new_df['最新計費期間'] != ''].groupby('電號')['最新計費期間'].last().to_dict()
    result_df['最新計費期間'] = result_df['電號'].map(latest_periods).fillna(result_df['最新計費期間'])

    # 排序
    result_df['sort_month'] = result_df['月份'].str.replace('月', '').astype(float).astype(int, errors='ignore')
    result_df = result_df.sort_values(by=['電號', '年份', 'sort_month'])
    result_df = result_df.drop(columns=['sort_month'])
    
    return result_df


def merge_errors(base_err, new_err, successful_data):
    """合併錯誤清單，並自動移除這次已經成功爬取的店家"""
    if new_err.empty: return base_err
    if base_err.empty: return new_err
    
    # 把新錯誤疊在舊錯誤上面，並去除重複電號 (保留最新錯誤訊息)
    combined_err = pd.concat([new_err, base_err], ignore_index=True)
    combined_err['電號'] = combined_err['電號'].astype(str).str.replace(".0", "", regex=False)
    combined_err = combined_err.drop_duplicates(subset=['電號'], keep='first')
    
    # 洗白邏輯：如果這個電號成功出現在最終資料中，代表他沒錯了，從錯誤名單中踢除
    if not successful_data.empty and '電號' in successful_data.columns:
        successful_ids = set(successful_data['電號'].astype(str))
        combined_err = combined_err[~combined_err['電號'].isin(successful_ids)]
            
    return combined_err


# --- 主執行區 ---
if __name__ == "__main__":
    
    # ==========================================
    # 1. 選擇「基準」舊檔案
    # ==========================================
    print(f"--- 正在從 '{MERGE_FOLDER_PATH}' 尋找基準檔案 ---")
    try:
        # 過濾出 xlsx 檔案，並排除開啟中產生的暫存檔 (~$)
        base_files = [f for f in os.listdir(MERGE_FOLDER_PATH) if f.endswith('.xlsx') and not f.startswith('~$')]
    except FileNotFoundError:
        print(f"❌ 找不到基準檔案資料夾 '{MERGE_FOLDER_PATH}'")
        exit()

    if not base_files:
        print("❌ 在資料夾中沒有找到任何 Excel 檔案作為基準。")
        exit()

    print("請選擇要作為「基準」的歷史資料庫檔案：")
    base_files = sorted(base_files, reverse=True) 
    for i, filename in enumerate(base_files): 
        print(f"  [{i+1}] {filename}")

    while True:
        try:
            choice = int(input("請輸入基準檔案編號: "))
            if 1 <= choice <= len(base_files):
                chosen_base_file = base_files[choice - 1]
                break
            else:
                print("輸入無效，請重新輸入。")
        except ValueError:
            print("請輸入數字。")

    BASE_EXCEL_PATH = os.path.join(MERGE_FOLDER_PATH, chosen_base_file)
    print(f"\n✅ 您已選擇基準檔案: {chosen_base_file}\n")


    # ==========================================
    # 2. 選擇「最新爬取」的新檔案
    # ==========================================
    print(f"--- 正在從 '{NEW_FILES_FOLDER_PATH}' 尋找最新爬取結果 ---")
    try:
        new_files = [f for f in os.listdir(NEW_FILES_FOLDER_PATH) if f.endswith('.xlsx') and f.startswith('爬取結果') and not f.startswith('~$')]
    except FileNotFoundError:
        print(f"❌ 找不到新檔案資料夾 '{NEW_FILES_FOLDER_PATH}'")
        exit()

    if not new_files:
        print("❌ 在 output 資料夾中沒有找到任何爬取結果。")
        exit()

    print("請選擇要用來更新資料庫的爬蟲檔案：")
    new_files = sorted(new_files, reverse=True) 
    for i, filename in enumerate(new_files): 
        print(f"  [{i+1}] {filename}")

    while True:
        try:
            choice = int(input("請輸入檔案編號: "))
            if 1 <= choice <= len(new_files):
                chosen_new_file = new_files[choice - 1]
                break
            else:
                print("輸入無效，請重新輸入。")
        except ValueError:
            print("請輸入數字。")

    NEW_FILE_PATH = os.path.join(NEW_FILES_FOLDER_PATH, chosen_new_file)
    print(f"\n✅ 您已選擇新檔案: {chosen_new_file}\n")


    # ==========================================
    # 3. 讀取資料並執行合併
    # ==========================================
    print(f"正在讀取基準檔案: {BASE_EXCEL_PATH}")
    try:
        df_old_sheets = pd.read_excel(BASE_EXCEL_PATH, sheet_name=None, keep_default_na=False, dtype=str)
        df_base_data, df_base_errors = find_sheets(df_old_sheets)
    except Exception as e:
        print(f"❌ 錯誤：讀取基準檔案失敗 - {e}")
        exit()

    print(f"正在讀取新爬取資料: {NEW_FILE_PATH}")
    try:
        df_new_sheets = pd.read_excel(NEW_FILE_PATH, sheet_name=None, keep_default_na=False, dtype=str)
        df_new_data, df_new_errors = find_sheets(df_new_sheets)
    except Exception as e:
        print(f"❌ 錯誤：讀取新檔案失敗 - {e}")
        exit()

    # 執行精準合併
    final_data = merge_tidy_data(df_base_data, df_new_data)
    final_errors = merge_errors(df_base_errors, df_new_errors, final_data)

    # ==========================================
    # 4. 寫入最終合併檔案
    # ==========================================
    if not final_data.empty or not final_errors.empty:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        new_filename = f"合併結果_{timestamp}.xlsx"
        
        # 存回 MERGE_FOLDER_PATH (也就是 .../merge 資料夾)
        os.makedirs(MERGE_FOLDER_PATH, exist_ok=True)
        new_output_path = os.path.join(MERGE_FOLDER_PATH, new_filename)
        
        print(f"\n正在寫入最終更新檔案: {new_output_path}")
        try:
            with pd.ExcelWriter(new_output_path, engine="openpyxl") as writer:
                if not final_data.empty:
                    final_data.to_excel(writer, index=False, sheet_name="台電歷年電費")
                if not final_errors.empty:
                    final_errors.to_excel(writer, index=False, sheet_name="爬取失敗名單")
                    
            print(f"🎉 合併大功告成！請至資料夾查看: {new_output_path}")
        except Exception as e:
            print(f"❌ 錯誤：儲存合併檔案失敗 - {e}")
    else:
        print("沒有任何資料可供合併。")