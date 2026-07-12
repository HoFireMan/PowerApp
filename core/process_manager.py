# 檔案路徑: core/process_manager.py
import subprocess
import threading
import os
import sys

class ProcessManager:
    def __init__(self, logger):
        self.logger = logger
        self.processes = {"api": None, "scraper": None}

    def run_script_in_thread(self, script_path, cwd, args, process_type, on_start=None, on_finish=None):
        """以背景執行緒啟動外部程式 (自動判斷 Python 腳本或獨立 exe)，並即時擷取輸出"""
        # 確保所有參數都是字串格式
        args = [str(a) for a in (args or [])] 
        
        # 💡 核心修改：智慧判斷執行方式
        if script_path.lower().endswith('.exe'):
            cmd = [script_path] + args  # 是 exe 就直接執行
        else:
            cmd = [sys.executable, script_path] + args # 是 py 就加上 python
            
        self.logger.log(f"系統：準備執行 {os.path.basename(script_path)}...\n參數: {args}\n" + "-"*50)
        
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        def task():
            if on_start: on_start()
            try:
                process = subprocess.Popen(
                    cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, encoding='utf-8', errors='replace', env=env, bufsize=1 
                )
                
                self.processes[process_type] = process
                
                buffer = ""
                while True:
                    char = process.stdout.read(1)
                    if not char and process.poll() is not None:
                        break
                    
                    if char in ('\r', '\n'):
                        if buffer.strip():
                            self.logger.log(buffer)
                            buffer = ""
                    else:
                        buffer += char
                
                process.wait()
                if process.returncode != 0:
                    self.logger.log("-" * 50 + f"\n系統：任務中斷或結束 (代碼: {process.returncode})\n")
                else:
                    self.logger.log("-" * 50 + f"\n✅ 系統：任務順利完成\n")
            except Exception as e:
                self.logger.log(f"\n系統錯誤：無法啟動程序 - {e}\n")
            finally:
                self.processes[process_type] = None
                if on_finish: on_finish()

        threading.Thread(target=task, daemon=True).start()

    def run_command(self, cmd_str, cwd, success_msg=None, fail_msg=None, on_finish=None):
        """執行純指令 (例如 docker)"""
        self.logger.log(f"系統：準備執行指令...\n" + "-"*50)
        def task():
            try:
                process = subprocess.Popen(cmd_str, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', shell=True)
                for line in process.stdout: 
                    self.logger.log(line.strip('\n'))
                process.wait()
                if process.returncode == 0 and success_msg:
                    self.logger.log("-" * 50 + f"\n✅ 系統：{success_msg}\n")
                elif process.returncode != 0 and fail_msg:
                    self.logger.log("-" * 50 + f"\n❌ {fail_msg} (代碼: {process.returncode})。\n")
            except Exception as e:
                self.logger.log(f"\n系統錯誤：執行指令失敗 - {e}\n")
            finally:
                if on_finish: on_finish()
        threading.Thread(target=task, daemon=True).start()

    def stop_process(self, process_type):
        """強制擊殺指定的進程"""
        proc = self.processes.get(process_type)
        if proc:
            self.logger.log(f"系統：正在強制終止 {process_type} 程序...")
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                self.logger.log(f"✅ 系統：{process_type} 程序已強制終止。\n")
            except Exception as e:
                self.logger.log(f"終止程序時發生錯誤: {e}")

    def stop_all(self):
        """關閉程式時的全面清理"""
        for p_type in self.processes:
            self.stop_process(p_type)