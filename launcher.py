"""
能源管理自動化系統 - 多執行緒爬蟲模組

Author: HoFireMan
GitHub: https://github.com/HoFireMan
Date: 2026-06-19
Description: 此模組負責串接感測器 API，並將資料併發寫入 PostgreSQL。
未經國立虎尾科技大學雲林縣節電團隊授權，請勿將本系統用於商業營利行為。
"""
import subprocess
import os
import sys

def main():
    # --- 1. 自動獲取當前執行檔/腳本所在的目錄 ---
    if getattr(sys, 'frozen', False):
        # 如果是打包後的 exe 執行
        base_dir = os.path.dirname(sys.executable)
    else:
        # 如果是 python 腳本執行
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    gui_script = os.path.join(base_dir, "main_gui.py")
    
    # --- 2. 智慧尋找 Anaconda 路徑 ---
    # 自動猜測幾種常見的 Anaconda 安裝路徑 (包含使用者名稱不同時)
    user_profile = os.environ.get('USERPROFILE', 'C:\\')
    possible_conda_paths = [
        os.path.join(user_profile, "anaconda3", "Scripts", "activate.bat"),
        os.path.join(user_profile, "miniconda3", "Scripts", "activate.bat"),
        r"C:\ProgramData\anaconda3\Scripts\activate.bat",
        r"C:\anaconda3\Scripts\activate.bat"
    ]
    
    activate_bat = None
    for path in possible_conda_paths:
        if os.path.exists(path):
            activate_bat = path
            break
            
    if not activate_bat:
        # 找不到的話，將錯誤寫入日誌並退出
        with open(os.path.join(base_dir, "launcher_error.log"), "w", encoding="utf-8") as f:
            f.write("錯誤：找不到 Anaconda 啟動腳本 (activate.bat)，請確認是否安裝了 Anaconda。\n")
        return

    env_name = "scraper_env"
    
    # --- 3. 執行邏輯 ---
    command = f'cmd /c "call "{activate_bat}" {env_name} && cd /d "{base_dir}" && python "{gui_script}""'
    
    creationflags = 0
    if os.name == 'nt':
        creationflags = subprocess.CREATE_NO_WINDOW
        
    log_path = os.path.join(base_dir, "launcher_error.log")
    with open(log_path, "w", encoding="utf-8") as log_file:
        subprocess.Popen(command, creationflags=creationflags, stdout=log_file, stderr=subprocess.STDOUT)

if __name__ == "__main__":
    main()