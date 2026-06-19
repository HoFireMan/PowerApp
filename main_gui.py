import customtkinter as ctk
import subprocess
import threading
import sys
import os

# --- 設定外觀 ---
ctk.set_appearance_mode("Dark")  # 預設深色模式
ctk.set_default_color_theme("blue")  # 主題顏色

# --- 專案路徑設定 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_SCRIPT_DIR = os.path.join(BASE_DIR, "Energy Report Automation")
SCRAPER_SCRIPT_DIR = os.path.join(BASE_DIR, "electricity_bill_scraper")

# 檔案與資料夾路徑
API_EXCEL_PATH = os.path.join(API_SCRIPT_DIR, "店家ID.xlsx")
ACCOUNTS_CSV_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "accounts.csv")
OUTPUT_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "output")
HISTORY_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "歷史爬取資料")

class PowerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("⚡ 能源管理與自動化中控台 v1.6")
        self.geometry("980x900")  # 稍微加大以容納新增的按鈕
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)  # 讓日誌視窗自動延展
        self.grid_rowconfigure(3, weight=0)  # 底部的開關列保持固定高度

        # 💡 新增：進程追蹤變數，用來記憶當前正在執行的程序
        self.current_api_process = None
        self.current_scraper_process = None

        # ==========================================
        # 頂部區塊：核心任務執行區
        # ==========================================
        # ------------------------------------------
        # 左側卡片：感測器 API 系統
        # ------------------------------------------
        self.frame_api = ctk.CTkFrame(self)
        self.frame_api.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        self.lbl_api = ctk.CTkLabel(self.frame_api, text="🔌 感測器 API 系統", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_api.pack(pady=(10, 5))
        
        # 獨立的「執行參數設定區」卡片
        self.api_param_container = ctk.CTkFrame(self.frame_api)
        self.api_param_container.pack(pady=(5, 10), padx=20, fill="x")

        self.lbl_api_param_title = ctk.CTkLabel(self.api_param_container, text="⚙️ 執行參數設定區", font=ctk.CTkFont(weight="bold"), text_color="#17a2b8")
        self.lbl_api_param_title.pack(pady=(5, 0))

        self.api_param_frame = ctk.CTkFrame(self.api_param_container, fg_color="transparent")
        self.api_param_frame.pack(pady=5)
        
        years = [str(y) for y in range(2020, 2031)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days = [f"{d:02d}" for d in range(1, 32)]
        threads = ["1", "3", "5", "10", "15", "20", "30"]

        # 起始日期下拉選單
        ctk.CTkLabel(self.api_param_frame, text="起始日期:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        frame_start = ctk.CTkFrame(self.api_param_frame, fg_color="transparent")
        frame_start.grid(row=0, column=1, sticky="w")
        
        self.cb_start_y = ctk.CTkComboBox(frame_start, values=years, width=70)
        self.cb_start_y.set("2020")
        self.cb_start_y.pack(side="left", padx=(0, 2))
        self.cb_start_m = ctk.CTkComboBox(frame_start, values=months, width=60)
        self.cb_start_m.set("05")
        self.cb_start_m.pack(side="left", padx=2)
        self.cb_start_d = ctk.CTkComboBox(frame_start, values=days, width=60)
        self.cb_start_d.set("20")
        self.cb_start_d.pack(side="left", padx=2)
        
        # 結束日期下拉選單
        ctk.CTkLabel(self.api_param_frame, text="結束日期:").grid(row=1, column=0, padx=5, pady=2, sticky="e")
        frame_end = ctk.CTkFrame(self.api_param_frame, fg_color="transparent")
        frame_end.grid(row=1, column=1, sticky="w")
        
        self.cb_end_y = ctk.CTkComboBox(frame_end, values=years, width=70)
        self.cb_end_y.set("2026")
        self.cb_end_y.pack(side="left", padx=(0, 2))
        self.cb_end_m = ctk.CTkComboBox(frame_end, values=months, width=60)
        self.cb_end_m.set("06")
        self.cb_end_m.pack(side="left", padx=2)
        self.cb_end_d = ctk.CTkComboBox(frame_end, values=days, width=60)
        self.cb_end_d.set("01")
        self.cb_end_d.pack(side="left", padx=2)
        
        # 間隔天數
        ctk.CTkLabel(self.api_param_frame, text="間隔天數:").grid(row=2, column=0, padx=5, pady=2, sticky="e")
        self.entry_step_days = ctk.CTkEntry(self.api_param_frame, width=200)
        self.entry_step_days.insert(0, "60")
        self.entry_step_days.grid(row=2, column=1, padx=2, pady=2, sticky="w")

        # API 核心數
        ctk.CTkLabel(self.api_param_frame, text="執行核心數:").grid(row=3, column=0, padx=5, pady=2, sticky="e")
        self.cb_threads = ctk.CTkComboBox(self.api_param_frame, values=threads, width=200)
        self.cb_threads.set("10")
        self.cb_threads.grid(row=3, column=1, padx=2, pady=2, sticky="w")

        # 開關資料庫按鈕
        self.btn_start_db = ctk.CTkButton(self.frame_api, text="🐳 開啟節電資料儲存伺服器", command=self.start_docker_db, fg_color="#e67e22", hover_color="#d35400")
        self.btn_start_db.pack(pady=(5, 2))
        
        self.btn_stop_db = ctk.CTkButton(self.frame_api, text="🛑 關閉節電資料儲存伺服器", command=self.stop_docker_db, fg_color="#dc3545", hover_color="#c82333")
        self.btn_stop_db.pack(pady=(2, 10))
        
        # 執行/終止 API 爬蟲按鈕 (將這兩個按鈕放在一起)
        self.btn_run_api = ctk.CTkButton(self.frame_api, text="▶ 啟動 API 抓取並寫入 DB", command=self.run_api_script, fg_color="#28a745", hover_color="#218838")
        self.btn_run_api.pack(pady=(5, 2))
        
        # 💡 新增：API 終止按鈕 (預設反灰)
        self.btn_stop_api = ctk.CTkButton(self.frame_api, text="⏹️ 強制終止 API 抓取", command=self.stop_api_script, fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_api.pack(pady=(2, 5))
        
        # 資料庫狀態
        self.lbl_api_status = ctk.CTkLabel(self.frame_api, text="⏳ 正在檢查資料庫狀態...", text_color="orange", font=ctk.CTkFont(weight="bold"))
        self.lbl_api_status.pack(pady=5)


        # ------------------------------------------
        # 右側卡片：台電帳單爬蟲系統
        # ------------------------------------------
        self.frame_scraper = ctk.CTkFrame(self)
        self.frame_scraper.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.lbl_scraper = ctk.CTkLabel(self.frame_scraper, text="🌐 台電帳單爬蟲系統", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_scraper.pack(pady=(10, 5))
        
        # 獨立的「執行參數設定區」卡片
        self.scraper_param_container = ctk.CTkFrame(self.frame_scraper)
        self.scraper_param_container.pack(pady=(5, 10), padx=20, fill="x")

        self.lbl_scraper_param_title = ctk.CTkLabel(self.scraper_param_container, text="⚙️ 執行參數設定區", font=ctk.CTkFont(weight="bold"), text_color="#17a2b8")
        self.lbl_scraper_param_title.pack(pady=(5, 0))

        self.scraper_param_frame = ctk.CTkFrame(self.scraper_param_container, fg_color="transparent")
        self.scraper_param_frame.pack(pady=5)

        ctk.CTkLabel(self.scraper_param_frame, text="瀏覽器數量:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.cb_browsers = ctk.CTkComboBox(self.scraper_param_frame, values=["1", "2", "3", "4", "5", "6", "8", "10"], width=120)
        self.cb_browsers.set("3")
        self.cb_browsers.grid(row=0, column=1, padx=5, pady=2, sticky="w")

        self.lbl_browser_hint = ctk.CTkLabel(self.scraper_param_container, text="💡 建議 3 或以內，如果穩定可以選擇更高", text_color="gray", font=ctk.CTkFont(size=12))
        self.lbl_browser_hint.pack(pady=(0, 10))

        # 執行/終止 台電爬蟲與合併按鈕
        self.btn_run_scraper = ctk.CTkButton(self.frame_scraper, text="▶ 啟動網頁爬蟲 (最新電費)", command=self.run_scraper_script, fg_color="#007bff", hover_color="#0069d9")
        self.btn_run_scraper.pack(pady=(15, 2))
        
        # 💡 新增：台電爬蟲終止按鈕 (預設反灰)
        self.btn_stop_scraper = ctk.CTkButton(self.frame_scraper, text="⏹️ 強制終止網頁爬蟲", command=self.stop_scraper_script, fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_scraper.pack(pady=(2, 10))

        self.btn_run_merge = ctk.CTkButton(self.frame_scraper, text="📂 執行 Excel 資料合併", command=self.run_merge_script, fg_color="#17a2b8", hover_color="#138496")
        self.btn_run_merge.pack(pady=10)

        # ==========================================
        # 中間區塊：檔案與目錄快速存取區 (分為左右兩側)
        # ==========================================
        # 左側：感測器 API 捷徑
        self.frame_api_shortcuts = ctk.CTkFrame(self)
        self.frame_api_shortcuts.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        self.lbl_api_shortcuts = ctk.CTkLabel(self.frame_api_shortcuts, text="📁 感測器API快速存取區", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_api_shortcuts.pack(pady=(10, 5))

        self.btn_open_api_dir = ctk.CTkButton(self.frame_api_shortcuts, text="📂 開啟專案資料夾", command=lambda: self.open_path(API_SCRIPT_DIR), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_api_dir.pack(pady=5, padx=30, fill="x")

        self.btn_open_api_excel = ctk.CTkButton(self.frame_api_shortcuts, text="📝 開啟/修改店家ID清單", command=lambda: self.open_path(API_EXCEL_PATH), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_api_excel.pack(pady=5, padx=30, fill="x")

        # 右側：台電帳單捷徑
        self.frame_scraper_shortcuts = ctk.CTkFrame(self)
        self.frame_scraper_shortcuts.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="nsew")
        
        self.lbl_scraper_shortcuts = ctk.CTkLabel(self.frame_scraper_shortcuts, text="📁 台電帳單快速存取區", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_scraper_shortcuts.pack(pady=(10, 5))

        self.btn_open_accounts = ctk.CTkButton(self.frame_scraper_shortcuts, text="📝 新增/修改電號名稱", command=lambda: self.open_path(ACCOUNTS_CSV_PATH), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_accounts.pack(pady=5, padx=30, fill="x")

        self.btn_open_output = ctk.CTkButton(self.frame_scraper_shortcuts, text="📁 爬蟲 Excel 儲存位置", command=lambda: self.open_path(OUTPUT_FOLDER_PATH), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_output.pack(pady=5, padx=30, fill="x")

        self.btn_open_history = ctk.CTkButton(self.frame_scraper_shortcuts, text="📁 資料合併歷史位置", command=lambda: self.open_path(HISTORY_FOLDER_PATH), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_history.pack(pady=5, padx=30, fill="x")

        # ==========================================
        # 底部區塊：即時日誌視窗、版權宣告與主題切換
        # ==========================================
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13))
        self.log_textbox.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="nsew")

        # 💡 新增：作者版權宣告 (置於左下角)
        self.lbl_author = ctk.CTkLabel(
            self, 
            text="© 2026 Developed by HoFireMan\n國立虎尾科技大學 節電團隊", 
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="gray"
        )
        self.lbl_author.grid(row=3, column=0, padx=15, pady=(5, 10), sticky="w")

        self.switch_theme = ctk.CTkSwitch(self, text="深色模式 🌙", command=self.toggle_theme_mode, font=ctk.CTkFont(weight="bold"))
        self.switch_theme.select()
        self.switch_theme.grid(row=3, column=1, padx=15, pady=(5, 10), sticky="e")

        self.check_db_status()

    # --- 核心邏輯區 ---
    def toggle_theme_mode(self):
        if self.switch_theme.get() == 1:
            ctk.set_appearance_mode("Dark")
            self.switch_theme.configure(text="深色模式 🌙")
        else:
            ctk.set_appearance_mode("Light")
            self.switch_theme.configure(text="淺色模式 ☀️")

    def check_db_status(self):
        self.lbl_api_status.configure(text="⏳ 正在檢查資料庫狀態...", text_color="orange")
        def task():
            try:
                result = subprocess.run('docker ps -q -f "name=energy_db"', shell=True, capture_output=True, text=True)
                if bool(result.stdout.strip()):
                    self.after(0, lambda: self.lbl_api_status.configure(text="🟢 資料庫狀態：執行中", text_color="#28a745"))
                    self.after(0, self.log, "系統：偵測到節電資料庫 (Docker) 已在背景執行中。")
                else:
                    self.after(0, lambda: self.lbl_api_status.configure(text="🔴 資料庫狀態：未啟動", text_color="#dc3545"))
                    self.after(0, self.log, "系統：節電資料庫尚未啟動，請點擊上方【開啟伺服器】按鈕。")
            except Exception as e:
                self.after(0, lambda: self.lbl_api_status.configure(text="🔴 資料庫狀態：偵測失敗", text_color="#dc3545"))
                self.after(0, self.log, f"系統錯誤：無法偵測 Docker 狀態 ({e})")
        threading.Thread(target=task, daemon=True).start()

    def log(self, message):
        self.log_textbox.configure(state="normal")
        clean_msg = message.replace('\r', '')
        if not clean_msg:
            self.log_textbox.configure(state="disabled")
            return
        last_line_start = self.log_textbox.index("end-2c linestart")
        last_line_text = self.log_textbox.get(last_line_start, "end-1c")

        if "總進度:" in clean_msg and "%|" in clean_msg:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                self.log_textbox.delete(last_line_start, "end-1c")
                self.log_textbox.insert(ctk.END, clean_msg)
            else:
                self.log_textbox.insert(ctk.END, clean_msg)
        else:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                self.log_textbox.insert(ctk.END, "\n" + clean_msg + "\n")
            else:
                self.log_textbox.insert(ctk.END, clean_msg + "\n")

        self.log_textbox.see(ctk.END)
        self.log_textbox.configure(state="disabled")

    def open_path(self, path):
        if os.path.exists(path):
            self.log(f"系統：正在開啟 {path} ...")
            try: os.startfile(path)
            except Exception as e: self.log(f"❌ 無法開啟路徑: {e}")
        else:
            self.log(f"❌ 找不到路徑: {path}")

    def run_script_in_thread(self, script_path, cwd, args=None, process_type=None):
        """背景執行腳本並追蹤進程 (process_type 區分 api 或 scraper)"""
        args = args or []
        cmd = [sys.executable, script_path] + args
        self.log(f"系統：準備執行 {os.path.basename(script_path)}...\n參數: {args}\n" + "-"*50)
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        def task():
            try:
                process = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, encoding='utf-8', errors='replace', env=env
                )
                
                # 💡 啟動時紀錄進程並切換按鈕狀態 (防呆機制)
                if process_type == "api":
                    self.current_api_process = process
                    self.after(0, lambda: self.btn_run_api.configure(state="disabled"))
                    self.after(0, lambda: self.btn_stop_api.configure(state="normal"))
                elif process_type == "scraper":
                    self.current_scraper_process = process
                    self.after(0, lambda: self.btn_run_scraper.configure(state="disabled"))
                    self.after(0, lambda: self.btn_stop_scraper.configure(state="normal"))

                for line in process.stdout:
                    self.after(0, self.log, line.strip('\n'))
                
                process.wait()
                
                # 若自然執行結束(代碼0)，或被強制中止(代碼不為0)
                if process.returncode != 0:
                    self.after(0, self.log, "-"*50 + f"\n系統：任務中斷或結束 (代碼: {process.returncode})\n")
                else:
                    self.after(0, self.log, "-"*50 + f"\n✅ 系統：任務順利完成\n")
                    
            except Exception as e:
                self.after(0, self.log, f"\n系統錯誤：無法啟動程序 - {e}\n")
            finally:
                # 💡 無論如何，結束後恢復按鈕狀態，清除進程紀錄
                if process_type == "api":
                    self.current_api_process = None
                    self.after(0, lambda: self.btn_run_api.configure(state="normal"))
                    self.after(0, lambda: self.btn_stop_api.configure(state="disabled"))
                elif process_type == "scraper":
                    self.current_scraper_process = None
                    self.after(0, lambda: self.btn_run_scraper.configure(state="normal"))
                    self.after(0, lambda: self.btn_stop_scraper.configure(state="disabled"))

        threading.Thread(target=task, daemon=True).start()

    # --- 💡 新增：強制終止邏輯 ---
    def stop_api_script(self):
        """使用 taskkill 拔除整棵 API 進程樹"""
        if self.current_api_process:
            self.log("系統：正在強制終止 API 抓取程序...")
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.current_api_process.pid)], capture_output=True)
                self.log("✅ 系統：API 抓取程序已強制終止。\n")
            except Exception as e:
                self.log(f"終止程序時發生錯誤: {e}")

    def stop_scraper_script(self):
        """使用 taskkill 拔除整棵爬蟲進程樹 (包含殘留的 Chrome)"""
        if self.current_scraper_process:
            self.log("系統：正在強制終止網頁爬蟲程序與連帶的瀏覽器...")
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.current_scraper_process.pid)], capture_output=True)
                self.log("✅ 系統：網頁爬蟲程序已強制終止。\n")
            except Exception as e:
                self.log(f"終止程序時發生錯誤: {e}")

    # --- 按鈕綁定功能 ---
    def start_docker_db(self):
        self.log(f"系統：準備啟動 Docker 節電資料儲存伺服器...\n" + "-"*50)
        def task():
            try:
                process = subprocess.Popen("docker-compose up -d", cwd=API_SCRIPT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', shell=True)
                for line in process.stdout: self.after(0, self.log, line.strip('\n'))
                process.wait()
                if process.returncode == 0:
                    self.after(0, self.log, "-"*50 + "\n✅ 系統：資料庫伺服器已成功啟動！\n")
                else:
                    self.after(0, self.log, "-"*50 + f"\n❌ 啟動失敗 (代碼: {process.returncode})。\n")
                self.after(1000, self.check_db_status)
            except Exception as e:
                self.after(0, self.log, f"\n系統錯誤：無法啟動 Docker 程序 - {e}\n")
        threading.Thread(target=task, daemon=True).start()

    def stop_docker_db(self):
        self.log(f"系統：準備關閉 Docker 節電資料儲存伺服器...\n" + "-"*50)
        def task():
            try:
                process = subprocess.Popen("docker-compose down", cwd=API_SCRIPT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', shell=True)
                for line in process.stdout: self.after(0, self.log, line.strip('\n'))
                process.wait()
                if process.returncode == 0:
                    self.after(0, self.log, "-"*50 + "\n✅ 系統：資料庫伺服器已成功關閉與釋放資源！\n")
                else:
                    self.after(0, self.log, "-"*50 + f"\n❌ 關閉失敗 (代碼: {process.returncode})。\n")
                self.after(1000, self.check_db_status)
            except Exception as e:
                self.after(0, self.log, f"\n系統錯誤：無法關閉 Docker 程序 - {e}\n")
        threading.Thread(target=task, daemon=True).start()

    def run_api_script(self):
        script_path = os.path.join(API_SCRIPT_DIR, "sync_to_postgres_Multi-threading.py")
        if os.path.exists(script_path):
            start_date = f"{self.cb_start_y.get()}-{self.cb_start_m.get()}-{self.cb_start_d.get()}"
            end_date = f"{self.cb_end_y.get()}-{self.cb_end_m.get()}-{self.cb_end_d.get()}"
            step_days = self.entry_step_days.get()
            max_workers = self.cb_threads.get()
            # 💡 指定 process_type="api"
            self.run_script_in_thread(script_path, API_SCRIPT_DIR, args=[start_date, end_date, step_days, max_workers], process_type="api")
        else:
            self.log(f"❌ 找不到檔案: {script_path}")

    def run_scraper_script(self):
        script_path = os.path.join(SCRAPER_SCRIPT_DIR, "electricity_bill_scraper_v3.py")
        if os.path.exists(script_path):
            browsers_count = self.cb_browsers.get()
            # 💡 指定 process_type="scraper"
            self.run_script_in_thread(script_path, SCRAPER_SCRIPT_DIR, args=[browsers_count], process_type="scraper")
        else:
            self.log(f"❌ 找不到檔案: {script_path}")

    def run_merge_script(self):
        script_path = os.path.join(SCRAPER_SCRIPT_DIR, "merge_excel_files.py")
        if os.path.exists(script_path):
            self.log("系統：已開啟新的命令提示字元視窗來執行 Excel 合併...")
            subprocess.Popen(f'start cmd /k "{sys.executable}" "{script_path}"', cwd=SCRAPER_SCRIPT_DIR, shell=True)
        else:
            self.log(f"❌ 找不到檔案: {script_path}")

if __name__ == "__main__":
    app = PowerApp()
    app.mainloop()