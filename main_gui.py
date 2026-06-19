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

# 💡 新增：離線版瀏覽器與驅動目錄常數
OFFLINE_CHROME_DIR = os.path.join(BASE_DIR, "GoogleChromePortable")
OFFLINE_DRIVER_DIR = os.path.join(BASE_DIR, "chromedriver-win64")

class PowerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("⚡ 能源管理與自動化中控台 v1.7")
        self.geometry("980x900")  # 稍微加大以容納新增的按鈕
        
        # 💡 優化：設定視窗左上角與 Windows 工作列的圖示
        icon_path = os.path.join(BASE_DIR, "app.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)  # 設定視窗標題列圖示
            
            # 💡 隱藏絕招：強制 Windows 工作列將此視窗視為獨立應用程式 (覆蓋 Python 預設圖示)
            try:
                import ctypes
                myappid = 'hofireman.powerapp.v1.7' # 任意自訂的獨立 ID
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)  # 讓日誌視窗自動延展
        self.grid_rowconfigure(3, weight=0)  # 底部的開關列保持固定高度

        # 💡 優化 1：一啟動就確保必要的空資料夾存在，防止捷徑報錯
        os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
        os.makedirs(HISTORY_FOLDER_PATH, exist_ok=True)

        # 💡 優化 2：綁定視窗右上角的 "X" 關閉事件，防止產生殭屍進程
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 進程追蹤變數，用來記憶當前正在執行的程序
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

        self.btn_open_driver = ctk.CTkButton(self.frame_scraper_shortcuts, text="📁 網頁爬蟲驅動暫存區", command=self.open_driver_path, fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_driver.pack(pady=5, padx=30, fill="x")

        # ==========================================
        # 底部區塊：即時日誌視窗、版權宣告與主題切換
        # ==========================================
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13))
        self.log_textbox.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="nsew")

        # 💡 新增：設定日誌的專屬顏色標籤 (適用於深色模式的亮色系)
        self.log_textbox.tag_config("t1", foreground="#5DADE2") # 淺藍 (執行緒-1)
        self.log_textbox.tag_config("t2", foreground="#48C9B0") # 淺綠 (執行緒-2)
        self.log_textbox.tag_config("t3", foreground="#F4D03F") # 淺黃 (執行緒-3)
        self.log_textbox.tag_config("t4", foreground="#F5B041") # 橘色 (執行緒-4)
        self.log_textbox.tag_config("t5", foreground="#AF7AC5") # 紫色 (執行緒-5)
        self.log_textbox.tag_config("t6", foreground="#EC7063") # 紅色 (執行緒-6)
        self.log_textbox.tag_config("t7", foreground="#E59866") # 泥色 (執行緒-7)
        self.log_textbox.tag_config("t8", foreground="#AAB7B8") # 灰色 (執行緒-8)
        self.log_textbox.tag_config("t9", foreground="#FF69B4") # 粉紅 (執行緒-9)
        self.log_textbox.tag_config("t10", foreground="#58D68D")# 亮綠 (執行緒-10)
        self.log_textbox.tag_config("sys", foreground="#FDFEFE") # 白色 (系統提示)
        self.log_textbox.tag_config("err", foreground="#E74C3C") # 亮紅 (錯誤警告)
        self.log_textbox.tag_config("ok", foreground="#2ECC71")  # 亮綠 (成功訊息)

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

    def open_driver_path(self):
        if os.path.exists(OFFLINE_DRIVER_DIR):
            self.log(f"系統：偵測到離線驅動，開啟專案目錄...")
            self.open_path(OFFLINE_DRIVER_DIR)
        else:
            self.log(f"系統：未偵測到離線驅動，開啟系統預設暫存區...")
            driver_path = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
            if not os.path.exists(driver_path):
                try:
                    os.makedirs(driver_path)
                except Exception:
                    pass
            self.open_path(driver_path)

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

        # 💡 新增：自動判斷這行訊息屬於誰，並給予對應的顏色標籤
        tag = None
        if "[執行緒-1]" in clean_msg: tag = "t1"
        elif "[執行緒-2]" in clean_msg: tag = "t2"
        elif "[執行緒-3]" in clean_msg: tag = "t3"
        elif "[執行緒-4]" in clean_msg: tag = "t4"
        elif "[執行緒-5]" in clean_msg: tag = "t5"
        elif "[執行緒-6]" in clean_msg: tag = "t6"
        elif "[執行緒-7]" in clean_msg: tag = "t7"
        elif "[執行緒-8]" in clean_msg: tag = "t8"
        elif "[執行緒-9]" in clean_msg: tag = "t9"
        elif "[執行緒-10]" in clean_msg: tag = "t10"
        elif "系統：" in clean_msg or "準備執行" in clean_msg or "💡" in clean_msg: tag = "sys"
        elif "❌" in clean_msg or "錯誤" in clean_msg or "崩潰" in clean_msg: tag = "err"
        elif "✅" in clean_msg or "成功" in clean_msg: tag = "ok"

        last_line_start = self.log_textbox.index("end-2c linestart")
        last_line_text = self.log_textbox.get(last_line_start, "end-1c")

        if "總進度:" in clean_msg and "%|" in clean_msg:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                self.log_textbox.delete(last_line_start, "end-1c")
                if tag: self.log_textbox.insert(ctk.END, clean_msg, tags=tag)
                else: self.log_textbox.insert(ctk.END, clean_msg)
            else:
                if tag: self.log_textbox.insert(ctk.END, clean_msg, tags=tag)
                else: self.log_textbox.insert(ctk.END, clean_msg)
        else:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                if tag: self.log_textbox.insert(ctk.END, "\n" + clean_msg + "\n", tags=tag)
                else: self.log_textbox.insert(ctk.END, "\n" + clean_msg + "\n")
            else:
                if tag: self.log_textbox.insert(ctk.END, clean_msg + "\n", tags=tag)
                else: self.log_textbox.insert(ctk.END, clean_msg + "\n")

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
        args = args or []
        
        # 參數包含 -u 解除 print 緩衝限制
        cmd = [sys.executable, "-u", script_path] + args
        
        self.log(f"系統：準備執行 {os.path.basename(script_path)}...\n參數: {args}\n" + "-"*50)
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        
        def task():
            try:
                process = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, encoding='utf-8', errors='replace', env=env
                )
                
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
                
                if process.returncode != 0:
                    self.after(0, self.log, "-"*50 + f"\n系統：任務中斷或結束 (代碼: {process.returncode})\n")
                else:
                    self.after(0, self.log, "-"*50 + f"\n✅ 系統：任務順利完成\n")
                    
            except Exception as e:
                self.after(0, self.log, f"\n系統錯誤：無法啟動程序 - {e}\n")
            finally:
                if process_type == "api":
                    self.current_api_process = None
                    self.after(0, lambda: self.btn_run_api.configure(state="normal"))
                    self.after(0, lambda: self.btn_stop_api.configure(state="disabled"))
                elif process_type == "scraper":
                    self.current_scraper_process = None
                    self.after(0, lambda: self.btn_run_scraper.configure(state="normal"))
                    self.after(0, lambda: self.btn_stop_scraper.configure(state="disabled"))

        threading.Thread(target=task, daemon=True).start()

    # 💡 確保安全退出的清理邏輯
    def on_closing(self):
        """關閉程式時，自動清理背景仍在執行的爬蟲或API"""
        if self.current_api_process or self.current_scraper_process:
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", "\n系統：正在清理背景程序，準備關閉...\n")
            self.log_textbox.configure(state="disabled")
            self.update() # 強制刷新畫面讓使用者看到
            
            self.stop_api_script()
            self.stop_scraper_script()
            
        self.destroy()
        sys.exit(0)

    def stop_api_script(self):
        if self.current_api_process:
            self.log("系統：正在強制終止 API 抓取程序...")
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.current_api_process.pid)], capture_output=True)
                self.log("✅ 系統：API 抓取程序已強制終止。\n")
            except Exception as e:
                self.log(f"終止程序時發生錯誤: {e}")

    def stop_scraper_script(self):
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
            self.run_script_in_thread(script_path, API_SCRIPT_DIR, args=[start_date, end_date, step_days, max_workers], process_type="api")
        else:
            self.log(f"❌ 找不到檔案: {script_path}")

    def run_scraper_script(self):
        script_path = os.path.join(SCRAPER_SCRIPT_DIR, "electricity_bill_scraper_v3.py")
        if os.path.exists(script_path):
            self.log("\n" + "!"*50)
            if os.path.exists(OFFLINE_CHROME_DIR) and os.path.exists(OFFLINE_DRIVER_DIR):
                self.log("🚀 系統提醒：已偵測到「專屬離線版瀏覽器」。")
                self.log("本次執行將完全免疫防火牆阻擋與 Chrome 版本更新干擾！")
            else:
                self.log("💡 系統提醒：未偵測到離線瀏覽器，將使用系統預設模式 (會自動下載驅動)。")
                self.log("若發生 [SSL/ASN1: NOT_ENOUGH_DATA] 錯誤，請暫時切換至【手機網路】後再試！")
            self.log("!"*50 + "\n")
            
            browsers_count = self.cb_browsers.get()
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