import customtkinter as ctk
import tkinter as tk
from tkinter import ttk 
import subprocess
import threading
import sys
import os
import pandas as pd

# --- 設定外觀 ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
API_SCRIPT_DIR = os.path.join(BASE_DIR, "Energy Report Automation")
SCRAPER_SCRIPT_DIR = os.path.join(BASE_DIR, "electricity_bill_scraper")

API_EXCEL_PATH = os.path.join(API_SCRIPT_DIR, "店家ID.xlsx")
ACCOUNTS_CSV_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "accounts.csv")
OUTPUT_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "output")
HISTORY_FOLDER_PATH = os.path.join(SCRAPER_SCRIPT_DIR, "歷史爬取資料")

OFFLINE_CHROME_DIR = os.path.join(BASE_DIR, "GoogleChromePortable")
OFFLINE_DRIVER_DIR = os.path.join(BASE_DIR, "chromedriver-win64")

class PowerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("⚡ 能源管理與自動化中控台 v3.1 (智能檢測版)")
        self.geometry("1020x950")  
        
        icon_path = os.path.join(BASE_DIR, "app.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
            try:
                import ctypes
                myappid = 'hofireman.powerapp.v3.1'
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception:
                pass

        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure("TCombobox", fieldbackground="#343638", background="#2b2b2b", foreground="white", arrowcolor="white", bordercolor="#565b5e")
        self.option_add('*TCombobox*Listbox.background', '#343638')
        self.option_add('*TCombobox*Listbox.foreground', 'white')
        self.option_add('*TCombobox*Listbox.selectBackground', '#1f538d')
        self.option_add('*TCombobox*Listbox.selectForeground', 'white')
        self.option_add('*TCombobox*Listbox.font', ("Microsoft JhengHei", 12))

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)  
        self.grid_rowconfigure(3, weight=0)  

        os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
        os.makedirs(HISTORY_FOLDER_PATH, exist_ok=True)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.current_api_process = None
        self.current_scraper_process = None
        self.store_options_dict = {} 
        self.cached_store_options = [] 

        # ==========================================
        # 頂部左側：感測器 API 分類功能區
        # ==========================================
        self.frame_api = ctk.CTkFrame(self)
        self.frame_api.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        self.lbl_api = ctk.CTkLabel(self.frame_api, text="🔌 感測器 API 系統", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_api.pack(pady=(10, 0))

        # --- 全區共用參數 (日期) ---
        self.api_date_frame = ctk.CTkFrame(self.frame_api, fg_color="transparent")
        self.api_date_frame.pack(pady=10, padx=10, fill="x")
        
        years = [str(y) for y in range(2020, 2031)]
        months = [f"{m:02d}" for m in range(1, 13)]
        days = [f"{d:02d}" for d in range(1, 32)]

        ctk.CTkLabel(self.api_date_frame, text="開始日期:", text_color="#17a2b8", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=2, sticky="e")
        f_start = ctk.CTkFrame(self.api_date_frame, fg_color="transparent")
        f_start.grid(row=0, column=1, sticky="w")
        self.cb_start_y = ctk.CTkComboBox(f_start, values=years, width=70)
        self.cb_start_y.set("2020")
        self.cb_start_y.pack(side="left", padx=2)
        self.cb_start_m = ctk.CTkComboBox(f_start, values=months, width=60)
        self.cb_start_m.set("05")
        self.cb_start_m.pack(side="left", padx=2)
        self.cb_start_d = ctk.CTkComboBox(f_start, values=days, width=60)
        self.cb_start_d.set("20")
        self.cb_start_d.pack(side="left", padx=2)

        ctk.CTkLabel(self.api_date_frame, text="結束日期:", text_color="#17a2b8", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=5, pady=2, sticky="e")
        f_end = ctk.CTkFrame(self.api_date_frame, fg_color="transparent")
        f_end.grid(row=1, column=1, sticky="w")
        self.cb_end_y = ctk.CTkComboBox(f_end, values=years, width=70)
        self.cb_end_y.set("2026")
        self.cb_end_y.pack(side="left", padx=2)
        self.cb_end_m = ctk.CTkComboBox(f_end, values=months, width=60)
        self.cb_end_m.set("06")
        self.cb_end_m.pack(side="left", padx=2)
        self.cb_end_d = ctk.CTkComboBox(f_end, values=days, width=60)
        self.cb_end_d.set("01")
        self.cb_end_d.pack(side="left", padx=2)

        self.api_tabs = ctk.CTkTabview(self.frame_api)
        self.api_tabs.pack(pady=5, padx=15, fill="both", expand=True)
        
        self.tab_fetch = self.api_tabs.add("📥 數據抓取")
        self.tab_check = self.api_tabs.add("🩺 數據檢測")
        self.tab_server = self.api_tabs.add("⚙️ 伺服器管理")

        # === Tab 1: 數據抓取設定 ===
        ctk.CTkLabel(self.tab_fetch, text="間隔天數:").grid(row=0, column=0, padx=5, pady=(5,2), sticky="e")
        self.entry_step_days = ctk.CTkEntry(self.tab_fetch, width=200)
        self.entry_step_days.insert(0, "30")
        self.entry_step_days.grid(row=0, column=1, padx=2, pady=(5,2), sticky="w")

        self.lbl_threads = ctk.CTkLabel(self.tab_fetch, text="執行核心數:")
        self.lbl_threads.grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.cb_threads = ctk.CTkComboBox(self.tab_fetch, values=["1", "3", "5", "10", "15", "20", "30"], width=200)
        self.cb_threads.set("10")
        self.cb_threads.grid(row=1, column=1, padx=2, pady=2, sticky="w")

        self.switch_api_mode = ctk.CTkSwitch(
            self.tab_fetch, text="🎯 啟用 [指定店家] 模式", 
            command=self.toggle_api_mode, font=ctk.CTkFont(weight="bold"), progress_color="#e74c3c"
        )
        self.switch_api_mode.grid(row=2, column=0, columnspan=2, pady=(10, 5), padx=25, sticky="w")
        
        self.frame_store_labels = ctk.CTkFrame(self.tab_fetch, fg_color="transparent")
        self.frame_store_labels.grid(row=3, column=0, padx=5, pady=2, sticky="ne")
        self.lbl_store_id = ctk.CTkLabel(self.frame_store_labels, text="目標店家:", text_color="gray")
        self.lbl_store_id.pack(anchor="e")
        self.btn_add_store = ctk.CTkButton(self.frame_store_labels, text="➕ 新增", width=50, height=24, command=lambda: self.add_store_row(disabled=False), state="disabled")
        self.btn_add_store.pack(anchor="e", pady=(5, 0))
        
        self.store_list_frame = ctk.CTkFrame(self.tab_fetch, fg_color="transparent")
        self.store_list_frame.grid(row=3, column=1, sticky="w")
        
        self.store_rows = []
        self.add_store_row(disabled=True)

        self.btn_run_api = ctk.CTkButton(self.tab_fetch, text="▶ 啟動全部店家抓取", command=self.run_api_script, fg_color="#28a745", hover_color="#218838")
        self.btn_run_api.grid(row=4, column=0, columnspan=2, pady=(15, 5))
        self.btn_stop_api = ctk.CTkButton(self.tab_fetch, text="⏹️ 強制終止 API 抓取", command=self.stop_api_script, fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_api.grid(row=5, column=0, columnspan=2, pady=(2, 5))

        # === Tab 2: 數據檢測功能 ===
        lbl_check_title = ctk.CTkLabel(self.tab_check, text="📊 數據空缺與斷層檢測", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_check_title.pack(pady=(10, 5))
        
        lbl_check_desc = ctk.CTkLabel(self.tab_check, text="自動比對資料庫找出「幽靈店家」與「少報天數」設備。\n將會產出 Excel 報告並將摘要同步寫入資料庫日誌表。", justify="center", text_color="gray")
        lbl_check_desc.pack(pady=(0, 10))

        # 💡 新增：全時段打勾選項
        self.chk_all_time = ctk.CTkCheckBox(self.tab_check, text="✨ 全時段自動檢測 (自動抓取資料庫最早至最新紀錄，無視上方日期)", font=ctk.CTkFont(weight="bold"), fg_color="#9b59b6", hover_color="#8e44ad")
        self.chk_all_time.pack(pady=(5, 15))

        self.btn_run_check = ctk.CTkButton(self.tab_check, text="🔍 執行數據空缺檢測", command=self.run_check_script, fg_color="#9b59b6", hover_color="#8e44ad")
        self.btn_run_check.pack(pady=5)

        # === Tab 3: 伺服器管理 ===
        self.btn_start_db = ctk.CTkButton(self.tab_server, text="🐳 開啟節電資料儲存伺服器", command=self.start_docker_db, fg_color="#e67e22", hover_color="#d35400")
        self.btn_start_db.pack(pady=(30, 10))
        
        self.btn_stop_db = ctk.CTkButton(self.tab_server, text="🛑 關閉節電資料儲存伺服器", command=self.stop_docker_db, fg_color="#dc3545", hover_color="#c82333")
        self.btn_stop_db.pack(pady=10)

        self.lbl_api_status = ctk.CTkLabel(self.tab_server, text="⏳ 正在檢查資料庫狀態...", text_color="orange", font=ctk.CTkFont(weight="bold"))
        self.lbl_api_status.pack(pady=20)


        # ------------------------------------------
        # 頂部右側：台電帳單爬蟲系統
        # ------------------------------------------
        self.frame_scraper = ctk.CTkFrame(self)
        self.frame_scraper.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.lbl_scraper = ctk.CTkLabel(self.frame_scraper, text="🌐 台電帳單爬蟲系統", font=ctk.CTkFont(size=18, weight="bold"))
        self.lbl_scraper.pack(pady=(10, 5))
        
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

        self.btn_run_scraper = ctk.CTkButton(self.frame_scraper, text="▶ 啟動網頁爬蟲 (最新電費)", command=self.run_scraper_script, fg_color="#007bff", hover_color="#0069d9")
        self.btn_run_scraper.pack(pady=(15, 2))
        
        self.btn_stop_scraper = ctk.CTkButton(self.frame_scraper, text="⏹️ 強制終止網頁爬蟲", command=self.stop_scraper_script, fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_scraper.pack(pady=(2, 10))

        self.btn_run_merge = ctk.CTkButton(self.frame_scraper, text="📂 執行 Excel 資料合併", command=self.run_merge_script, fg_color="#17a2b8", hover_color="#138496")
        self.btn_run_merge.pack(pady=10)

        # ==========================================
        # 中間區塊：檔案與目錄快速存取區
        # ==========================================
        self.frame_api_shortcuts = ctk.CTkFrame(self)
        self.frame_api_shortcuts.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        self.lbl_api_shortcuts = ctk.CTkLabel(self.frame_api_shortcuts, text="📁 感測器API快速存取區", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_api_shortcuts.pack(pady=(10, 5))

        self.btn_open_api_dir = ctk.CTkButton(self.frame_api_shortcuts, text="📂 開啟專案資料夾", command=lambda: self.open_path(API_SCRIPT_DIR), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_api_dir.pack(pady=5, padx=30, fill="x")

        self.btn_open_api_excel = ctk.CTkButton(self.frame_api_shortcuts, text="📝 開啟/修改店家ID清單", command=lambda: self.open_path(API_EXCEL_PATH), fg_color="#6c757d", hover_color="#5a6268")
        self.btn_open_api_excel.pack(pady=5, padx=30, fill="x")

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
        # 底部區塊：即時日誌視窗與色彩標籤
        # ==========================================
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13))
        self.log_textbox.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="nsew")

        self.log_textbox.tag_config("t1", foreground="#5DADE2") 
        self.log_textbox.tag_config("t2", foreground="#48C9B0") 
        self.log_textbox.tag_config("t3", foreground="#F4D03F") 
        self.log_textbox.tag_config("t4", foreground="#F5B041") 
        self.log_textbox.tag_config("t5", foreground="#AF7AC5") 
        self.log_textbox.tag_config("t6", foreground="#EC7063") 
        self.log_textbox.tag_config("t7", foreground="#E59866") 
        self.log_textbox.tag_config("t8", foreground="#AAB7B8") 
        self.log_textbox.tag_config("t9", foreground="#FF69B4") 
        self.log_textbox.tag_config("t10", foreground="#58D68D")
        self.log_textbox.tag_config("sys", foreground="#FDFEFE") 
        self.log_textbox.tag_config("err", foreground="#E74C3C") 
        self.log_textbox.tag_config("ok", foreground="#2ECC71")  

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
    
    def add_store_row(self, disabled=False, initial_value=""):
        row_frame = ctk.CTkFrame(self.store_list_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=(0, 5))

        cb = ttk.Combobox(row_frame, width=15, font=("Microsoft JhengHei", 12))
        
        if not self.cached_store_options:
            self.load_store_options()
        cb['values'] = self.cached_store_options

        if disabled:
            cb.insert(0, "請先開啟單店模式")
            cb.configure(state="disabled")
        else:
            cb.configure(state="normal")
            if initial_value:
                cb.set(initial_value)
            elif self.cached_store_options and "無資料" not in self.cached_store_options[0] and "錯誤" not in self.cached_store_options[0]:
                cb.set(self.cached_store_options[0])

        cb.pack(side="left", padx=(2, 5))

        lbl_hint = ctk.CTkLabel(row_frame, text="", text_color="gray", font=ctk.CTkFont(size=12))
        lbl_hint.pack(side="left", padx=(0, 5))

        row_data = {"frame": row_frame, "cb": cb, "lbl": lbl_hint}

        if not disabled and len(self.store_rows) >= 1:
            btn_del = ctk.CTkButton(row_frame, text="❌", width=28, height=24, fg_color="#dc3545", hover_color="#c82333",
                                    command=lambda r=row_data: self.remove_store_row(r))
            btn_del.pack(side="left")

        self.store_rows.append(row_data)

        if not disabled:
            def on_change(event=None, combobox=cb, label=lbl_hint):
                current_text = combobox.get()
                if " - " in current_text:
                    parts = current_text.split(" - ", 1)
                    combobox.set(parts[0].strip())
                    label.configure(text=f"({parts[1].strip()})")
                    combobox.icursor(tk.END)
                else:
                    store_id = current_text.strip()
                    if store_id in self.store_options_dict:
                        name = self.store_options_dict[store_id]
                        label.configure(text=f"({name})" if name else "")
                    else:
                        label.configure(text="")

            cb.bind("<<ComboboxSelected>>", on_change)
            cb.bind("<KeyRelease>", on_change)
            on_change()

    def remove_store_row(self, row_data):
        row_data["frame"].destroy()
        if row_data in self.store_rows:
            self.store_rows.remove(row_data)

    def load_store_options(self):
        self.store_options_dict = {} 
        
        if not os.path.exists(API_EXCEL_PATH):
            self.cached_store_options = ["讀取失敗: 找不到店家清單"]
            return self.cached_store_options
            
        try:
            df = pd.read_excel(API_EXCEL_PATH, sheet_name="店家資訊", dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            
            if "ID" not in df.columns:
                self.cached_store_options = ["錯誤: 找不到欄位 [ID]"]
                return self.cached_store_options
                
            name_col = None
            possible_names = ["name", "店名", "店家名稱", "店家的名稱", "門市名稱", "名稱", "公司名稱"]
            for col in df.columns:
                if str(col).lower() in possible_names:
                    name_col = col
                    break
                    
            if not name_col and len(df.columns) >= 2:
                id_idx = df.columns.get_loc("ID")
                if id_idx + 1 < len(df.columns):
                    name_col = df.columns[id_idx + 1]
                    
            options = []
            for _, row in df.iterrows():
                sid = str(row["ID"]).strip()
                if sid == "nan" or not sid: 
                    continue
                
                sname = ""
                if name_col and pd.notna(row[name_col]):
                    sname = str(row[name_col]).strip()
                    options.append(f"{sid} - {sname}")
                else:
                    options.append(sid)
                
                self.store_options_dict[sid] = sname
                    
            self.cached_store_options = options if options else ["清單內無資料"]
            return self.cached_store_options
            
        except Exception as e:
            self.cached_store_options = ["讀取失敗: 檔案被佔用或格式錯誤"]
            return self.cached_store_options

    def toggle_api_mode(self):
        if self.switch_api_mode.get() == 1:
            self.cb_threads.configure(state="disabled")
            self.lbl_threads.configure(text_color="gray")
            
            for row in self.store_rows:
                row["frame"].destroy()
            self.store_rows.clear()
            
            self.load_store_options()
            self.btn_add_store.configure(state="normal")
            self.lbl_store_id.configure(text_color=["black", "white"])
            self.add_store_row(disabled=False)
                
            self.btn_run_api.configure(text="▶ 啟動【選定店家】補抓", fg_color="#e74c3c", hover_color="#c0392b")
        else:
            self.cb_threads.configure(state="normal")
            self.lbl_threads.configure(text_color=["black", "white"])
            
            for row in self.store_rows:
                row["frame"].destroy()
            self.store_rows.clear()
            
            self.btn_add_store.configure(state="disabled")
            self.lbl_store_id.configure(text_color="gray")
            self.add_store_row(disabled=True)
            
            self.btn_run_api.configure(text="▶ 啟動全部店家抓取", fg_color="#28a745", hover_color="#218838")

    def toggle_theme_mode(self):
        if self.switch_theme.get() == 1:
            ctk.set_appearance_mode("Dark")
            self.switch_theme.configure(text="深色模式 🌙")
            self.style.configure("TCombobox", fieldbackground="#343638", background="#2b2b2b", foreground="white", arrowcolor="white")
            self.option_add('*TCombobox*Listbox.background', '#343638')
            self.option_add('*TCombobox*Listbox.foreground', 'white')
        else:
            ctk.set_appearance_mode("Light")
            self.switch_theme.configure(text="淺色模式 ☀️")
            self.style.configure("TCombobox", fieldbackground="#f9f9fa", background="#e5e5e5", foreground="black", arrowcolor="black")
            self.option_add('*TCombobox*Listbox.background', '#f9f9fa')
            self.option_add('*TCombobox*Listbox.foreground', 'black')

    def open_driver_path(self):
        if os.path.exists(OFFLINE_DRIVER_DIR):
            self.log(f"系統：偵測到離線驅動，開啟專案目錄...")
            self.open_path(OFFLINE_DRIVER_DIR)
        else:
            self.log(f"系統：未偵測到離線驅動，開啟系統預設暫存區...")
            driver_path = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
            if not os.path.exists(driver_path):
                try: os.makedirs(driver_path)
                except Exception: pass
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
        elif "✅" in clean_msg or "成功" in clean_msg or "🎉" in clean_msg: tag = "ok"

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
        cmd = [sys.executable, script_path] + args
        self.log(f"系統：準備執行 {os.path.basename(script_path)}...\n參數: {args}\n" + "-"*50)
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        def task():
            try:
                process = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, encoding='utf-8', errors='replace', env=env,
                    bufsize=1 
                )
                
                if process_type == "api":
                    self.current_api_process = process
                    self.after(0, lambda: self.btn_run_api.configure(state="disabled"))
                    self.after(0, lambda: self.btn_stop_api.configure(state="normal"))
                elif process_type == "scraper":
                    self.current_scraper_process = process
                    self.after(0, lambda: self.btn_run_scraper.configure(state="disabled"))
                    self.after(0, lambda: self.btn_stop_scraper.configure(state="normal"))

                buffer = ""
                while True:
                    char = process.stdout.read(1)
                    if not char and process.poll() is not None:
                        break
                    
                    if char in ('\r', '\n'):
                        if buffer.strip():
                            self.after(0, self.log, buffer)
                            buffer = ""
                    else:
                        buffer += char
                
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

    def on_closing(self):
        if self.current_api_process or self.current_scraper_process:
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", "\n系統：正在清理背景程序，準備關閉...\n")
            self.log_textbox.configure(state="disabled")
            self.update() 
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

    def start_docker_db(self):
        self.log(f"系統：準備啟動 Docker 節電資料儲存伺服器...\n" + "-"*50)
        def task():
            try:
                env_path = os.path.join(BASE_DIR, ".env")
                cmd = f'docker-compose --env-file "{env_path}" up -d'
                
                process = subprocess.Popen(cmd, cwd=API_SCRIPT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', shell=True)
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
                env_path = os.path.join(BASE_DIR, ".env")
                cmd = f'docker-compose --env-file "{env_path}" down'
                
                process = subprocess.Popen(cmd, cwd=API_SCRIPT_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', shell=True)
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
        start_date = f"{self.cb_start_y.get()}-{self.cb_start_m.get()}-{self.cb_start_d.get()}"
        end_date = f"{self.cb_end_y.get()}-{self.cb_end_m.get()}-{self.cb_end_d.get()}"
        step_days = self.entry_step_days.get()

        if self.switch_api_mode.get() == 1:
            script_path = os.path.join(API_SCRIPT_DIR, "fetch_single_store.py")
            
            valid_ids = []
            for row in self.store_rows:
                raw_store_selection = row["cb"].get().strip()
                store_id = raw_store_selection.split(" - ")[0].strip()
                if store_id and "請先開啟" not in store_id and "讀取失敗" not in store_id and "錯誤" not in store_id and "無資料" not in store_id:
                    valid_ids.append(store_id)
            
            if not valid_ids:
                self.log("❌ 錯誤：請至少選擇或輸入一個有效的目標店家 ID！")
                return
                
            store_ids_str = ",".join(valid_ids)
                
            if os.path.exists(script_path):
                self.run_script_in_thread(script_path, API_SCRIPT_DIR, args=[start_date, end_date, step_days, store_ids_str], process_type="api")
            else:
                self.log(f"❌ 找不到檔案: {script_path}")
        else:
            script_path = os.path.join(API_SCRIPT_DIR, "sync_to_postgres_Multi-threading.py")
            max_workers = self.cb_threads.get()
            
            if os.path.exists(script_path):
                self.run_script_in_thread(script_path, API_SCRIPT_DIR, args=[start_date, end_date, step_days, max_workers], process_type="api")
            else:
                self.log(f"❌ 找不到檔案: {script_path}")

    # 💡 呼叫空缺檢測程式的功能 (加入全時段判斷)
    def run_check_script(self):
        # 如果勾選了「全時段」，就把參數設為 ALL
        if self.chk_all_time.get() == 1:
            start_date = "ALL"
            end_date = "ALL"
        else:
            start_date = f"{self.cb_start_y.get()}-{self.cb_start_m.get()}-{self.cb_start_d.get()}"
            end_date = f"{self.cb_end_y.get()}-{self.cb_end_m.get()}-{self.cb_end_d.get()}"
        
        script_path = os.path.join(API_SCRIPT_DIR, "check_missing_sensor_data.py")
        if os.path.exists(script_path):
            self.run_script_in_thread(script_path, API_SCRIPT_DIR, args=[start_date, end_date], process_type="api")
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