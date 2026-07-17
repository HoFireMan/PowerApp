# 檔案路徑: gui/components.py
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
import pandas as pd
import os
import subprocess
import sys
import threading
from core import config

class ApiFetchTab(ctk.CTkFrame):
    def __init__(self, master, get_dates_cb, process_manager):
        super().__init__(master, fg_color="transparent")
        self.get_dates_cb = get_dates_cb
        self.pm = process_manager
        
        self.store_options_dict = {}
        self.cached_store_options = []
        self.store_rows = []

        # --- UI 建構 ---
        ctk.CTkLabel(self, text="間隔天數:").grid(row=0, column=0, padx=5, pady=(5,2), sticky="e")
        self.entry_step_days = ctk.CTkEntry(self, width=200)
        self.entry_step_days.insert(0, "30")
        self.entry_step_days.grid(row=0, column=1, padx=2, pady=(5,2), sticky="w")

        self.lbl_threads = ctk.CTkLabel(self, text="執行核心數:")
        self.lbl_threads.grid(row=1, column=0, padx=5, pady=2, sticky="e")
        self.cb_threads = ctk.CTkComboBox(self, values=config.THREADS, width=200)
        self.cb_threads.set("10")
        self.cb_threads.grid(row=1, column=1, padx=2, pady=2, sticky="w")

        self.switch_api_mode = ctk.CTkSwitch(
            self, text="🎯 啟用 [指定店家] 模式", 
            command=self.toggle_api_mode, font=ctk.CTkFont(weight="bold"), progress_color="#e74c3c"
        )
        self.switch_api_mode.grid(row=2, column=0, columnspan=2, pady=(10, 5), padx=25, sticky="w")
        
        self.frame_store_labels = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_store_labels.grid(row=3, column=0, padx=5, pady=2, sticky="ne")
        self.lbl_store_id = ctk.CTkLabel(self.frame_store_labels, text="目標店家:", text_color="gray")
        self.lbl_store_id.pack(anchor="e")
        self.btn_add_store = ctk.CTkButton(self.frame_store_labels, text="➕ 新增", width=50, height=24, command=lambda: self.add_store_row(disabled=False), state="disabled")
        self.btn_add_store.pack(anchor="e", pady=(5, 0))
        
        self.store_list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.store_list_frame.grid(row=3, column=1, sticky="w")
        
        self.add_store_row(disabled=True)

        self.btn_run_api = ctk.CTkButton(self, text="▶ 啟動全部店家抓取", command=self.run_api_script, fg_color="#28a745", hover_color="#218838")
        self.btn_run_api.grid(row=4, column=0, columnspan=2, pady=(15, 5))
        self.btn_stop_api = ctk.CTkButton(self, text="⏹️ 強制終止 API 抓取", command=lambda: self.pm.stop_process("api"), fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_api.grid(row=5, column=0, columnspan=2, pady=(2, 5))

    # --- 內部邏輯 ---
    def add_store_row(self, disabled=False, initial_value=""):
        row_frame = ctk.CTkFrame(self.store_list_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=(0, 5))

        cb = ttk.Combobox(row_frame, width=15, font=("Microsoft JhengHei", 12))
        if not self.cached_store_options: self.load_store_options()
        cb['values'] = self.cached_store_options

        if disabled:
            cb.insert(0, "請先開啟單店模式")
            cb.configure(state="disabled")
        else:
            cb.configure(state="normal")
            if initial_value: cb.set(initial_value)
            elif self.cached_store_options and "無資料" not in self.cached_store_options[0]: cb.set(self.cached_store_options[0])

        cb.pack(side="left", padx=(2, 5))

        lbl_hint = ctk.CTkLabel(row_frame, text="", text_color="gray", font=ctk.CTkFont(size=12))
        lbl_hint.pack(side="left", padx=(0, 5))

        row_data = {"frame": row_frame, "cb": cb, "lbl": lbl_hint}

        if not disabled and len(self.store_rows) >= 1:
            btn_del = ctk.CTkButton(row_frame, text="❌", width=28, height=24, fg_color="#dc3545", hover_color="#c82333", command=lambda r=row_data: self.remove_store_row(r))
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
                    name = self.store_options_dict.get(store_id, "")
                    label.configure(text=f"({name})" if name else "")

            cb.bind("<<ComboboxSelected>>", on_change)
            cb.bind("<KeyRelease>", on_change)
            on_change()

    def remove_store_row(self, row_data):
        row_data["frame"].destroy()
        if row_data in self.store_rows: self.store_rows.remove(row_data)

    def load_store_options(self):
        self.store_options_dict = {} 
        if not os.path.exists(config.API_EXCEL_PATH):
            self.cached_store_options = ["讀取失敗: 找不到店家清單"]
            return
            
        try:
            df = pd.read_excel(config.API_EXCEL_PATH, sheet_name="店家資訊", dtype=str)
            df.columns = [str(c).strip() for c in df.columns]
            name_col = next((c for c in df.columns if str(c).lower() in ["name", "店名", "店家名稱", "門市名稱", "名稱", "公司名稱"]), None)
            if not name_col and len(df.columns) >= 2: name_col = df.columns[df.columns.get_loc("ID") + 1]
                    
            options = []
            for _, row in df.iterrows():
                sid = str(row["ID"]).strip()
                if sid == "nan" or not sid: continue
                sname = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else ""
                options.append(f"{sid} - {sname}" if sname else sid)
                self.store_options_dict[sid] = sname
                    
            self.cached_store_options = options if options else ["清單內無資料"]
        except Exception:
            self.cached_store_options = ["讀取失敗: 檔案格式錯誤"]

    def toggle_api_mode(self):
        for row in self.store_rows: row["frame"].destroy()
        self.store_rows.clear()

        if self.switch_api_mode.get() == 1:
            self.cb_threads.configure(state="disabled")
            self.lbl_threads.configure(text_color="gray")
            self.load_store_options()
            self.btn_add_store.configure(state="normal")
            self.lbl_store_id.configure(text_color=["black", "white"])
            self.add_store_row(disabled=False)
            self.btn_run_api.configure(text="▶ 啟動【選定店家】補抓", fg_color="#e74c3c", hover_color="#c0392b")
        else:
            self.cb_threads.configure(state="normal")
            self.lbl_threads.configure(text_color=["black", "white"])
            self.btn_add_store.configure(state="disabled")
            self.lbl_store_id.configure(text_color="gray")
            self.add_store_row(disabled=True)
            self.btn_run_api.configure(text="▶ 啟動全部店家抓取", fg_color="#28a745", hover_color="#218838")

    def run_api_script(self):
        dates = self.get_dates_cb()
        step_days = self.entry_step_days.get()

        # 💡 指向 Go 語言編譯出來的 .exe
        script_path = os.path.join(config.API_SCRIPT_DIR, "api_fetcher.exe")

        if self.switch_api_mode.get() == 1:
            valid_ids = [r["cb"].get().split(" - ")[0].strip() for r in self.store_rows if r["cb"].get().strip() and "請先開啟" not in r["cb"].get()]
            if not valid_ids:
                self.pm.logger.log("❌ 錯誤：請至少選擇或輸入一個有效的目標店家 ID！")
                return
            args = [dates['start'], dates['end'], step_days, "10", ",".join(valid_ids)]
        else:
            args = [dates['start'], dates['end'], step_days, self.cb_threads.get(), "ALL"]

        if os.path.exists(script_path):
            self.pm.run_script_in_thread(
                script_path, config.API_SCRIPT_DIR, args, "api",
                on_start=lambda: (self.btn_run_api.configure(state="disabled"), self.btn_stop_api.configure(state="normal")),
                on_finish=lambda: (self.btn_run_api.configure(state="normal"), self.btn_stop_api.configure(state="disabled"))
            )
        else:
            self.pm.logger.log(f"❌ 找不到執行檔: {script_path} \n💡 請先在該目錄下執行 'go build -o api_fetcher.exe api_fetcher.go' 進行編譯！")


class ApiCheckTab(ctk.CTkFrame):
    def __init__(self, master, get_dates_cb, process_manager):
        super().__init__(master, fg_color="transparent")
        self.get_dates_cb = get_dates_cb
        self.pm = process_manager

        lbl_check_title = ctk.CTkLabel(self, text="📊 數據空缺與斷層檢測", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_check_title.pack(pady=(10, 5))
        lbl_check_desc = ctk.CTkLabel(self, text="自動比對資料庫找出「幽靈店家」與「少報天數」設備。\n將會產出 Excel 報告並將摘要同步寫入資料庫日誌表。", justify="center", text_color="gray")
        lbl_check_desc.pack(pady=(0, 10))

        self.chk_all_time = ctk.CTkCheckBox(self, text="✨ 全時段自動檢測 (無視上方日期，自動抓取最舊至最新)", font=ctk.CTkFont(weight="bold"), fg_color="#9b59b6", hover_color="#8e44ad")
        self.chk_all_time.pack(pady=(5, 10))

        self.chk_auto_fix = ctk.CTkCheckBox(self, text="🛠️ 檢測後自動啟動【多執行緒重抓】與【強制補 0】機制", font=ctk.CTkFont(weight="bold"), fg_color="#e74c3c", hover_color="#c0392b")
        self.chk_auto_fix.pack(pady=(5, 15))

        self.btn_run_check = ctk.CTkButton(self, text="🔍 執行數據空缺檢測", command=self.run_check_script, fg_color="#9b59b6", hover_color="#8e44ad")
        self.btn_run_check.pack(pady=5)

    def run_check_script(self):
        dates = {"start": "ALL", "end": "ALL"} if self.chk_all_time.get() == 1 else self.get_dates_cb()
        auto_fix_flag = "auto_fix" if self.chk_auto_fix.get() == 1 else "no_fix"
        
        # 💡 指向 Go 語言編譯出來的 .exe
        script_path = os.path.join(config.API_SCRIPT_DIR, "data_checker.exe")
        
        if os.path.exists(script_path):
            self.pm.run_script_in_thread(
                script_path, config.API_SCRIPT_DIR, [dates['start'], dates['end'], auto_fix_flag], "api",
                on_start=lambda: self.btn_run_check.configure(state="disabled"),
                on_finish=lambda: self.btn_run_check.configure(state="normal")
            )
        else:
            self.pm.logger.log(f"❌ 找不到執行檔: {script_path} \n💡 請先在該目錄下執行 'go build -o data_checker.exe data_checker.go' 進行編譯！")


class ServerTab(ctk.CTkFrame):
    def __init__(self, master, process_manager):
        super().__init__(master, fg_color="transparent")
        self.pm = process_manager

        self.btn_start_db = ctk.CTkButton(self, text="🐳 開啟節電資料儲存伺服器", command=self.start_docker, fg_color="#e67e22", hover_color="#d35400")
        self.btn_start_db.pack(pady=(30, 10))
        self.btn_stop_db = ctk.CTkButton(self, text="🛑 關閉節電資料儲存伺服器", command=self.stop_docker, fg_color="#dc3545", hover_color="#c82333")
        self.btn_stop_db.pack(pady=10)

        self.lbl_api_status = ctk.CTkLabel(self, text="⏳ 正在檢查資料庫狀態...", text_color="orange", font=ctk.CTkFont(weight="bold"))
        self.lbl_api_status.pack(pady=20)
        self.check_status_loop()

    def start_docker(self):
        # 💡 .env 依然在專案最外層，所以這裡維持 config.BASE_DIR
        cmd = f'docker-compose --env-file "{os.path.join(config.BASE_DIR, ".env")}" up -d'
        # 💡 告訴指令：請進到 database 資料夾裡面去執行 docker-compose
        db_dir = os.path.join(config.BASE_DIR, "database")
        self.pm.run_command(cmd, db_dir, "資料庫伺服器已成功啟動！", "啟動失敗", on_finish=self.check_status_loop)

    def stop_docker(self):
        cmd = f'docker-compose --env-file "{os.path.join(config.BASE_DIR, ".env")}" down'
        db_dir = os.path.join(config.BASE_DIR, "database")
        self.pm.run_command(cmd, db_dir, "資料庫伺服器已成功關閉與釋放資源！", "關閉失敗", on_finish=self.check_status_loop)

    def check_status_loop(self):
        def task():
            try:
                res = subprocess.run('docker ps -q -f "name=energy_db"', shell=True, capture_output=True, text=True)
                if bool(res.stdout.strip()):
                    self.lbl_api_status.configure(text="🟢 資料庫狀態：執行中", text_color="#28a745")
                else:
                    self.lbl_api_status.configure(text="🔴 資料庫狀態：未啟動", text_color="#dc3545")
            except:
                self.lbl_api_status.configure(text="🔴 資料庫狀態：偵測失敗", text_color="#dc3545")
        threading.Thread(target=task, daemon=True).start()


class ScraperPanel(ctk.CTkFrame):
    def __init__(self, master, process_manager):
        super().__init__(master)
        self.pm = process_manager

        ctk.CTkLabel(self, text="🌐 台電帳單爬蟲系統", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 5))
        
        param_container = ctk.CTkFrame(self)
        param_container.pack(pady=(5, 10), padx=20, fill="x")
        ctk.CTkLabel(param_container, text="⚙️ 執行參數設定區", font=ctk.CTkFont(weight="bold"), text_color="#17a2b8").pack(pady=(5, 0))

        param_frame = ctk.CTkFrame(param_container, fg_color="transparent")
        param_frame.pack(pady=5)
        ctk.CTkLabel(param_frame, text="瀏覽器數量:").grid(row=0, column=0, padx=5, pady=2, sticky="e")
        self.cb_browsers = ctk.CTkComboBox(param_frame, values=config.BROWSERS, width=120)
        self.cb_browsers.set("3")
        self.cb_browsers.grid(row=0, column=1, padx=5, pady=2, sticky="w")
        ctk.CTkLabel(param_container, text="💡 建議 3 或以內，如果穩定可以選擇更高", text_color="gray", font=ctk.CTkFont(size=12)).pack(pady=(0, 10))

        self.btn_run_scraper = ctk.CTkButton(self, text="▶ 啟動網頁爬蟲 (最新電費)", command=self.run_scraper, fg_color="#007bff", hover_color="#0069d9")
        self.btn_run_scraper.pack(pady=(15, 2))
        self.btn_stop_scraper = ctk.CTkButton(self, text="⏹️ 強制終止網頁爬蟲", command=lambda: self.pm.stop_process("scraper"), fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_scraper.pack(pady=(2, 10))

        ctk.CTkButton(self, text="📂 執行 Excel 資料合併", command=self.run_merge, fg_color="#17a2b8", hover_color="#138496").pack(pady=10)

    def run_scraper(self):
        # 💡 台電爬蟲維持 Python 架構
        script_path = os.path.join(config.SCRAPER_SCRIPT_DIR, "electricity_bill_scraper_v3.py")
        if os.path.exists(script_path):
            self.pm.logger.log("\n" + "!"*50)
            if os.path.exists(config.OFFLINE_CHROME_DIR) and os.path.exists(config.OFFLINE_DRIVER_DIR):
                self.pm.logger.log("🚀 系統提醒：已偵測到「專屬離線版瀏覽器」。\n本次執行將完全免疫防火牆阻擋與 Chrome 版本更新干擾！")
            else:
                self.pm.logger.log("💡 系統提醒：未偵測到離線瀏覽器，將使用系統預設模式。")
            self.pm.logger.log("!"*50 + "\n")
            
            self.pm.run_script_in_thread(
                script_path, config.SCRAPER_SCRIPT_DIR, [self.cb_browsers.get()], "scraper",
                on_start=lambda: (self.btn_run_scraper.configure(state="disabled"), self.btn_stop_scraper.configure(state="normal")),
                on_finish=lambda: (self.btn_run_scraper.configure(state="normal"), self.btn_stop_scraper.configure(state="disabled"))
            )

    def run_merge(self):
        script_path = os.path.join(config.SCRAPER_SCRIPT_DIR, "merge_excel_files.py")
        if os.path.exists(script_path):
            self.pm.logger.log("系統：已開啟新的命令提示字元視窗來執行 Excel 合併...")
            subprocess.Popen(f'start cmd /k "{sys.executable}" "{script_path}"', cwd=config.SCRAPER_SCRIPT_DIR, shell=True)


class ShortcutsPanel(ctk.CTkFrame):
    def __init__(self, master, process_manager):
        super().__init__(master, fg_color="transparent")
        self.pm = process_manager

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        f_api = ctk.CTkFrame(self)
        f_api.grid(row=0, column=0, padx=10, sticky="nsew")
        ctk.CTkLabel(f_api, text="📁 感測器API快速存取區", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        ctk.CTkButton(f_api, text="📂 開啟專案資料夾", command=lambda: self.open_path(config.API_SCRIPT_DIR), fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")
        ctk.CTkButton(f_api, text="📝 開啟/修改店家ID清單", command=lambda: self.open_path(config.API_EXCEL_PATH), fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")

        f_scr = ctk.CTkFrame(self)
        f_scr.grid(row=0, column=1, padx=10, sticky="nsew")
        ctk.CTkLabel(f_scr, text="📁 台電帳單快速存取區", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 5))
        ctk.CTkButton(f_scr, text="📝 新增/修改電號名稱", command=lambda: self.open_path(config.ACCOUNTS_CSV_PATH), fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")
        ctk.CTkButton(f_scr, text="📁 爬蟲 Excel 儲存位置", command=lambda: self.open_path(config.OUTPUT_FOLDER_PATH), fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")
        ctk.CTkButton(f_scr, text="📁 資料合併歷史位置", command=lambda: self.open_path(config.HISTORY_FOLDER_PATH), fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")
        ctk.CTkButton(f_scr, text="📁 網頁爬蟲驅動暫存區", command=self.open_driver, fg_color="#6c757d", hover_color="#5a6268").pack(pady=5, padx=30, fill="x")

    def open_path(self, path):
        if os.path.exists(path):
            self.pm.logger.log(f"系統：正在開啟 {path} ...")
            os.startfile(path)
        else:
            self.pm.logger.log(f"❌ 找不到路徑: {path}")

    def open_driver(self):
        if os.path.exists(config.OFFLINE_DRIVER_DIR):
            self.open_path(config.OFFLINE_DRIVER_DIR)
        else:
            driver_path = os.path.join(os.environ.get('APPDATA', ''), 'undetected_chromedriver')
            if not os.path.exists(driver_path): os.makedirs(driver_path, exist_ok=True)
            self.open_path(driver_path)


# ==========================================
# 全新獨立的自動化排程總管介面 (獨立區塊，彰顯全域控制權)
# ==========================================
class AutomationPanel(ctk.CTkFrame):
    def __init__(self, master, process_manager):
        super().__init__(master) # 這裡不用透明背景，讓它有一個實體的方塊感
        self.pm = process_manager
        
        # --- UI 建構 ---
        lbl_title = ctk.CTkLabel(self, text="🤖 系統全自動排程總管", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_title.pack(pady=(10, 5))
        
        lbl_desc = ctk.CTkLabel(self, text="將全套流程註冊至 Windows 排程器。每月指定時間將自動在背景無人值守執行：\n【API 抓取 ➔ 檢測補零 ➔ 台電帳單爬蟲】", justify="center", text_color="gray")
        lbl_desc.pack(pady=(0, 10))

        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(pady=5)
        
        ctk.CTkLabel(ctrl_frame, text="每月自動啟動時間:").pack(side="left", padx=5)
        
        self.cb_day = ctk.CTkComboBox(ctrl_frame, values=[str(i) for i in range(1, 29)], width=60)
        self.cb_day.set("1")
        self.cb_day.pack(side="left")
        
        ctk.CTkLabel(ctrl_frame, text="號  00:05").pack(side="left", padx=5)
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(5, 10))
        
        self.btn_register = ctk.CTkButton(btn_frame, text="📅 註冊至系統排程", command=self.register_task, fg_color="#28a745", hover_color="#218838")
        self.btn_register.pack(side="left", padx=10)
        
        self.btn_remove = ctk.CTkButton(btn_frame, text="🗑️ 移除自動排程", command=self.remove_task, fg_color="#dc3545", hover_color="#c82333")
        self.btn_remove.pack(side="left", padx=10)
        
        self.btn_test = ctk.CTkButton(btn_frame, text="🚀 立即手動測試全流程", command=self.run_pipeline_now, fg_color="#17a2b8", hover_color="#138496")
        self.btn_test.pack(side="left", padx=10)

        # 💡 新增：終止測試按鈕
        self.btn_stop_test = ctk.CTkButton(btn_frame, text="⏹️ 終止測試", command=self.stop_pipeline_now, fg_color="#dc3545", hover_color="#c82333", state="disabled")
        self.btn_stop_test.pack(side="left", padx=10)

    def register_task(self):
        day = self.cb_day.get()
        script_path = os.path.join(config.BASE_DIR, "auto_pipeline.py")
        
        # 建立執行 bat (包裝 python 指令與不顯示黑框的邏輯)
        bat_path = os.path.join(config.BASE_DIR, "run_pipeline_hidden.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(f'@echo off\n"{sys.executable}" "{script_path}"\n')

        # 💡 修改排程器啟動時間為凌晨 00:05
        cmd = f'schtasks /create /tn "PowerApp_Monthly_Auto" /tr "{bat_path}" /sc monthly /d {day} /st 00:05 /f'
        
        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            self.pm.logger.log(f"✅ 成功將自動化排程註冊至 Windows！\n系統將於每月 {day} 號凌晨 00:05 自動在背景執行完整任務。")
        except Exception as e:
            self.pm.logger.log(f"❌ 註冊排程失敗 (請確認是否以系統管理員身分執行): {e}")

    def remove_task(self):
        cmd = 'schtasks /delete /tn "PowerApp_Monthly_Auto" /f'
        try:
            subprocess.run(cmd, shell=True, check=True, capture_output=True)
            self.pm.logger.log("✅ 成功移除 Windows 背景排程任務！")
        except:
            self.pm.logger.log("⚠️ 移除失敗，或是該排程本來就不存在。")

    def run_pipeline_now(self):
        script_path = os.path.join(config.BASE_DIR, "auto_pipeline.py")
        if os.path.exists(script_path):
            self.pm.run_script_in_thread(
                script_path, config.BASE_DIR, [], "pipeline",
                on_start=lambda: (self.btn_test.configure(state="disabled"), self.btn_stop_test.configure(state="normal")),
                on_finish=lambda: (self.btn_test.configure(state="normal"), self.btn_stop_test.configure(state="disabled"))
            )
        else:
            self.pm.logger.log(f"❌ 找不到整合腳本: {script_path}")

    # 💡 新增：強制終止排程腳本的邏輯
    def stop_pipeline_now(self):
        self.pm.stop_process("pipeline")