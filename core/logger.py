# 檔案路徑: core/logger.py
import customtkinter as ctk

class AppLogger:
    def __init__(self, textbox: ctk.CTkTextbox):
        self.textbox = textbox
        self._setup_tags()

    def _setup_tags(self):
        """初始化所有的語法高亮色彩標籤"""
        self.textbox.tag_config("t1", foreground="#5DADE2") 
        self.textbox.tag_config("t2", foreground="#48C9B0") 
        self.textbox.tag_config("t3", foreground="#F4D03F") 
        self.textbox.tag_config("t4", foreground="#F5B041") 
        self.textbox.tag_config("t5", foreground="#AF7AC5") 
        self.textbox.tag_config("t6", foreground="#EC7063") 
        self.textbox.tag_config("t7", foreground="#E59866") 
        self.textbox.tag_config("t8", foreground="#AAB7B8") 
        self.textbox.tag_config("t9", foreground="#FF69B4") 
        self.textbox.tag_config("t10", foreground="#58D68D")
        self.textbox.tag_config("sys", foreground="#FDFEFE") 
        self.textbox.tag_config("err", foreground="#E74C3C") 
        self.textbox.tag_config("ok", foreground="#2ECC71")

    def log(self, message):
        """將訊息丟給 UI 執行緒去渲染"""
        self.textbox.after(0, self._insert_log, message)

    def _insert_log(self, message):
        """核心渲染與防洗頻邏輯"""
        self.textbox.configure(state="normal")
        clean_msg = message.replace('\r', '')
        if not clean_msg:
            self.textbox.configure(state="disabled")
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

        last_line_start = self.textbox.index("end-2c linestart")
        last_line_text = self.textbox.get(last_line_start, "end-1c")

        if "總進度:" in clean_msg and "%|" in clean_msg:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                self.textbox.delete(last_line_start, "end-1c")
                if tag: self.textbox.insert(ctk.END, clean_msg, tags=tag)
                else: self.textbox.insert(ctk.END, clean_msg)
            else:
                if tag: self.textbox.insert(ctk.END, clean_msg, tags=tag)
                else: self.textbox.insert(ctk.END, clean_msg)
        else:
            if "總進度:" in last_line_text and "%|" in last_line_text:
                if tag: self.textbox.insert(ctk.END, "\n" + clean_msg + "\n", tags=tag)
                else: self.textbox.insert(ctk.END, "\n" + clean_msg + "\n")
            else:
                if tag: self.textbox.insert(ctk.END, clean_msg + "\n", tags=tag)
                else: self.textbox.insert(ctk.END, clean_msg + "\n")

        self.textbox.see(ctk.END)
        self.textbox.configure(state="disabled")