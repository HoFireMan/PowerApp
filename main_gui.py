# 檔案路徑: main_gui.py
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk 
import os
import sys

# 匯入我們切分好的專業模組
from core import config
from core.logger import AppLogger
from core.process_manager import ProcessManager
# 💡 將 AutomationTab 改為 AutomationPanel
from gui.components import ApiFetchTab, ApiCheckTab, ServerTab, ScraperPanel, ShortcutsPanel, AutomationPanel

class PowerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # 1. 初始化主視窗與樣式
        self.title("⚡ 能源管理與自動化中控台 v4.0 (MVC 模組化版)")
        self.geometry("1020x950")  
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        self._setup_styles()
        
        # 確保必備資料夾存在
        os.makedirs(config.OUTPUT_FOLDER_PATH, exist_ok=True)
        os.makedirs(config.HISTORY_FOLDER_PATH, exist_ok=True)

        # 2. 建立核心大腦 (日誌與進程管理器)
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13))
        self.logger = AppLogger(self.log_textbox)
        self.pm = ProcessManager(self.logger)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 3. 版面切割 (Grid)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        # 💡 因為中間多塞了一行，日誌視窗會被擠到第3列，這裡要把自動擴展權重交給第3列
        self.grid_rowconfigure(3, weight=1)  

        # ==========================================
        # 左上方：共用日期區與 API 分頁模組
        # ==========================================
        frame_api = ctk.CTkFrame(self)
        frame_api.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(frame_api, text="🔌 感測器 API 系統", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 0))

        # 共用日期設定
        date_frame = ctk.CTkFrame(frame_api, fg_color="transparent")
        date_frame.pack(pady=10, padx=10, fill="x")
        
        ctk.CTkLabel(date_frame, text="開始日期:", text_color="#17a2b8", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=5, pady=2, sticky="e")
        fs = ctk.CTkFrame(date_frame, fg_color="transparent")
        fs.grid(row=0, column=1, sticky="w")
        self.cb_start_y = ctk.CTkComboBox(fs, values=config.YEARS, width=70); self.cb_start_y.set("2020"); self.cb_start_y.pack(side="left", padx=2)
        self.cb_start_m = ctk.CTkComboBox(fs, values=config.MONTHS, width=60); self.cb_start_m.set("05"); self.cb_start_m.pack(side="left", padx=2)
        self.cb_start_d = ctk.CTkComboBox(fs, values=config.DAYS, width=60); self.cb_start_d.set("20"); self.cb_start_d.pack(side="left", padx=2)

        ctk.CTkLabel(date_frame, text="結束日期:", text_color="#17a2b8", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=5, pady=2, sticky="e")
        fe = ctk.CTkFrame(date_frame, fg_color="transparent")
        fe.grid(row=1, column=1, sticky="w")
        self.cb_end_y = ctk.CTkComboBox(fe, values=config.YEARS, width=70); self.cb_end_y.set("2026"); self.cb_end_y.pack(side="left", padx=2)
        self.cb_end_m = ctk.CTkComboBox(fe, values=config.MONTHS, width=60); self.cb_end_m.set("06"); self.cb_end_m.pack(side="left", padx=2)
        self.cb_end_d = ctk.CTkComboBox(fe, values=config.DAYS, width=60); self.cb_end_d.set("01"); self.cb_end_d.pack(side="left", padx=2)

        # 裝載三大分頁組件 (注意：這裡已經把舊的自動化分頁拿掉了)
        self.api_tabs = ctk.CTkTabview(frame_api)
        self.api_tabs.pack(pady=5, padx=15, fill="both", expand=True)
        
        self.tab_fetch = ApiFetchTab(self.api_tabs.add("📥 數據抓取"), self.get_dates, self.pm)
        self.tab_fetch.pack(fill="both", expand=True)
        
        self.tab_check = ApiCheckTab(self.api_tabs.add("🩺 數據檢測"), self.get_dates, self.pm)
        self.tab_check.pack(fill="both", expand=True)
        
        self.tab_server = ServerTab(self.api_tabs.add("⚙️ 伺服器管理"), self.pm)
        self.tab_server.pack(fill="both", expand=True)

        # ==========================================
        # 右上方：台電帳單爬蟲模組
        # ==========================================
        self.panel_scraper = ScraperPanel(self, self.pm)
        self.panel_scraper.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")

        # ==========================================
        # 中間 (1)：🤖 全新獨立的自動化排程總管
        # ==========================================
        self.panel_automation = AutomationPanel(self, self.pm)
        self.panel_automation.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

        # ==========================================
        # 中間 (2)：快捷鍵模組
        # ==========================================
        self.panel_shortcuts = ShortcutsPanel(self, self.pm)
        self.panel_shortcuts.grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="nsew")

        # ==========================================
        # 底部：日誌視窗與主題切換
        # ==========================================
        self.log_textbox.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="nsew")

        ctk.CTkLabel(self, text="© 2026 Developed by HoFireMan\n國立虎尾科技大學 節電團隊", font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").grid(row=4, column=0, padx=15, pady=(5, 10), sticky="w")
        
        self.switch_theme = ctk.CTkSwitch(self, text="深色模式 🌙", command=self.toggle_theme, font=ctk.CTkFont(weight="bold"))
        self.switch_theme.select()
        self.switch_theme.grid(row=4, column=1, padx=15, pady=(5, 10), sticky="e")

    # --- 內部事件與方法 ---
    def get_dates(self):
        return {
            "start": f"{self.cb_start_y.get()}-{self.cb_start_m.get()}-{self.cb_start_d.get()}",
            "end": f"{self.cb_end_y.get()}-{self.cb_end_m.get()}-{self.cb_end_d.get()}"
        }

    def _setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure("TCombobox", fieldbackground="#343638", background="#2b2b2b", foreground="white", arrowcolor="white", bordercolor="#565b5e")
        self.option_add('*TCombobox*Listbox.background', '#343638')
        self.option_add('*TCombobox*Listbox.foreground', 'white')
        self.option_add('*TCombobox*Listbox.selectBackground', '#1f538d')
        self.option_add('*TCombobox*Listbox.selectForeground', 'white')
        self.option_add('*TCombobox*Listbox.font', ("Microsoft JhengHei", 12))

    def toggle_theme(self):
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

    def on_closing(self):
        self.logger.log("\n系統：正在清理背景程序，準備關閉...\n")
        self.update() 
        self.pm.stop_all()
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    app = PowerApp()
    app.mainloop()