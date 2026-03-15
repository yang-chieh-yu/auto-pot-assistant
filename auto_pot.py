import os
import sys
import time
import threading
import ctypes
import json  # 【新增】用來處理存檔的模組
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox

# 檢查是否安裝 keyboard 模組
try:
    import keyboard
except ImportError:
    print("錯誤: 請先安裝 keyboard 模組")
    print("請在終端機輸入: pip install keyboard")
    sys.exit(1)

# --- WinAPI 設定 ---
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

GetDC = user32.GetDC
GetDC.argtypes = [wintypes.HWND]
GetDC.restype = wintypes.HDC

ReleaseDC = user32.ReleaseDC
ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
ReleaseDC.restype = ctypes.c_int

GetPixel = gdi32.GetPixel
GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
GetPixel.restype = ctypes.c_uint

def resource_path(relative_path):
    """ 取得資源路徑 (打包用) """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_config_path():
    """ 取得設定檔 (config.json) 的存放路徑，確保它和 exe 放在一起 """
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, 'config.json')

class DualAutoPotApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("吃派") 
        self.root.geometry("560x520")
        
        # --- 綁定視窗關閉事件 ---
        # 當按下右上角 X 時，執行 self.on_closing 來存檔
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # --- 圖示設定 ---
        try:
            icon_path = resource_path("app_icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception as e:
            pass # 隱藏錯誤提示以免打擾

        # --- App ID ---
        try:
            myappid = 'mycompany.dualpot.version'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        # --- 核心參數 ---
        self.config_path = get_config_path()
        self.is_running = threading.Event()
        self.worker_thread = None
        
        self.last_hp_time = 0.0
        self.last_mp_time = 0.0
        self.trigger_cooldown = 0.4
        
        self.calibration_step = 0
        self.calib_target_var = tk.StringVar(value="HP")

        # --- 變數區 (HP) ---
        self.hp_threshold = tk.IntVar(value=70)
        self.hp_key = tk.StringVar(value="home")
        self.hp_y = tk.IntVar(value=0)
        self.hp_x_min = tk.IntVar(value=0)
        self.hp_x_max = tk.IntVar(value=0)

        # --- 變數區 (MP) ---
        self.mp_threshold = tk.IntVar(value=20)
        self.mp_key = tk.StringVar(value="page up")
        self.mp_y = tk.IntVar(value=0)
        self.mp_x_min = tk.IntVar(value=0)
        self.mp_x_max = tk.IntVar(value=0)

        self.status_var = tk.StringVar(value="已停止 (按 F7 開始/停止)")

        # 【新增】啟動時先嘗試讀取舊設定
        self._load_config()

        self._build_ui()
        self._register_hotkeys()

    # ================= 新增：存讀檔功能 =================
    def _load_config(self):
        """ 啟動時讀取設定檔 """
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                    self.hp_threshold.set(config.get('hp_threshold', 70))
                    self.hp_key.set(config.get('hp_key', 'home'))
                    self.hp_y.set(config.get('hp_y', 0))
                    self.hp_x_min.set(config.get('hp_x_min', 0))
                    self.hp_x_max.set(config.get('hp_x_max', 0))

                    self.mp_threshold.set(config.get('mp_threshold', 20))
                    self.mp_key.set(config.get('mp_key', 'page up'))
                    self.mp_y.set(config.get('mp_y', 0))
                    self.mp_x_min.set(config.get('mp_x_min', 0))
                    self.mp_x_max.set(config.get('mp_x_max', 0))
            except Exception as e:
                print(f"讀取設定失敗: {e}")

    def _save_config(self):
        """ 關閉時儲存設定檔 """
        config = {
            'hp_threshold': self.hp_threshold.get(),
            'hp_key': self.hp_key.get(),
            'hp_y': self.hp_y.get(),
            'hp_x_min': self.hp_x_min.get(),
            'hp_x_max': self.hp_x_max.get(),
            'mp_threshold': self.mp_threshold.get(),
            'mp_key': self.mp_key.get(),
            'mp_y': self.mp_y.get(),
            'mp_x_min': self.mp_x_min.get(),
            'mp_x_max': self.mp_x_max.get()
        }
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"儲存設定失敗: {e}")

    def on_closing(self):
        """ 當使用者按下右上角 X 關閉視窗時觸發 """
        self.stop()          # 1. 停止所有偵測動作
        self._save_config()  # 2. 把當前數字存進 config.json
        self.root.destroy()  # 3. 真正關閉視窗
    # ===================================================

    def _build_ui(self):
        style = ttk.Style()
        style.configure("Bold.TLabel", font=("Microsoft JhengHei", 10, "bold"))
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        # --- 1. HP 設定區塊 ---
        hp_frame = ttk.LabelFrame(main_frame, text="❤️ HP (紅水) 設定", padding=10)
        hp_frame.pack(fill="x", pady=5)

        ttk.Label(hp_frame, text="低於 % 喝水:").grid(row=0, column=0, sticky="w")
        ttk.Scale(hp_frame, from_=5, to=95, variable=self.hp_threshold, orient="horizontal", command=lambda v: self.hp_threshold.set(int(float(v)))).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(hp_frame, textvariable=self.hp_threshold).grid(row=0, column=2)
        
        ttk.Label(hp_frame, text="按鍵:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(hp_frame, textvariable=self.hp_key, width=12).grid(row=1, column=1, sticky="w", padx=10)

        # --- 2. MP 設定區塊 ---
        mp_frame = ttk.LabelFrame(main_frame, text="💙 MP (藍水) 設定", padding=10)
        mp_frame.pack(fill="x", pady=5)

        ttk.Label(mp_frame, text="低於 % 喝水:").grid(row=0, column=0, sticky="w")
        ttk.Scale(mp_frame, from_=5, to=95, variable=self.mp_threshold, orient="horizontal", command=lambda v: self.mp_threshold.set(int(float(v)))).grid(row=0, column=1, sticky="ew", padx=10)
        ttk.Label(mp_frame, textvariable=self.mp_threshold).grid(row=0, column=2)
        
        ttk.Label(mp_frame, text="按鍵:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(mp_frame, textvariable=self.mp_key, width=12).grid(row=1, column=1, sticky="w", padx=10)

        # --- 3. 座標校正區 ---
        calib_frame = ttk.LabelFrame(main_frame, text="📍 座標校正 (按 F9)", padding=10)
        calib_frame.pack(fill="x", pady=5)

        ttk.Label(calib_frame, text="請先選擇要校正的目標，再按 F9:").pack(anchor="w")
        r_frame = ttk.Frame(calib_frame)
        r_frame.pack(anchor="w", pady=5)
        ttk.Radiobutton(r_frame, text="校正 HP", variable=self.calib_target_var, value="HP", command=self._reset_step).pack(side="left", padx=10)
        ttk.Radiobutton(r_frame, text="校正 MP", variable=self.calib_target_var, value="MP", command=self._reset_step).pack(side="left", padx=10)

        coord_grid = ttk.Frame(calib_frame)
        coord_grid.pack(fill="x", pady=5)
        
        # HP 座標與重置按鈕
        ttk.Label(coord_grid, text="HP Y軸:").grid(row=0, column=0)
        ttk.Label(coord_grid, textvariable=self.hp_y, foreground="red").grid(row=0, column=1, padx=5)
        ttk.Label(coord_grid, text="範圍:").grid(row=0, column=2)
        ttk.Label(coord_grid, textvariable=self.hp_x_min, foreground="red").grid(row=0, column=3)
        ttk.Label(coord_grid, text="~").grid(row=0, column=4)
        ttk.Label(coord_grid, textvariable=self.hp_x_max, foreground="red").grid(row=0, column=5)
        ttk.Button(coord_grid, text="重置", command=self._reset_hp_coords, width=5).grid(row=0, column=6, padx=(15,0))

        # MP 座標與重置按鈕
        ttk.Label(coord_grid, text="MP Y軸:").grid(row=1, column=0, pady=5)
        ttk.Label(coord_grid, textvariable=self.mp_y, foreground="blue").grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(coord_grid, text="範圍:").grid(row=1, column=2, pady=5)
        ttk.Label(coord_grid, textvariable=self.mp_x_min, foreground="blue").grid(row=1, column=3, pady=5)
        ttk.Label(coord_grid, text="~").grid(row=1, column=4, pady=5)
        ttk.Label(coord_grid, textvariable=self.mp_x_max, foreground="blue").grid(row=1, column=5, pady=5)
        ttk.Button(coord_grid, text="重置", command=self._reset_mp_coords, width=5).grid(row=1, column=6, padx=(15,0), pady=5)

        # --- 4. 控制區 ---
        ctrl_frame = ttk.Frame(main_frame)
        ctrl_frame.pack(fill="x", pady=10)
        self.start_btn = ttk.Button(ctrl_frame, text="開始偵測 (F7)", command=self.toggle_start)
        self.start_btn.pack(side="left", fill="x", expand=True)
        
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground="black", font=("Arial", 10))
        self.status_label.pack(side="bottom", anchor="w")

    def _reset_hp_coords(self):
        self.hp_y.set(0)
        self.hp_x_min.set(0)
        self.hp_x_max.set(0)
        self.status_var.set("🧹 已清除 HP 座標 (停止偵測血量)")
        self.calibration_step = 0

    def _reset_mp_coords(self):
        self.mp_y.set(0)
        self.mp_x_min.set(0)
        self.mp_x_max.set(0)
        self.status_var.set("🧹 已清除 MP 座標 (停止偵測魔力)")
        self.calibration_step = 0

    def _reset_step(self):
        self.calibration_step = 0
        self.status_var.set(f"已切換至 {self.calib_target_var.get()} 校正模式，請按 F9")

    def _register_hotkeys(self):
        try:
            keyboard.add_hotkey("f7", self.toggle_start)
            keyboard.add_hotkey("f9", self._debug_mouse_pos)
        except Exception:
            pass

    def _debug_mouse_pos(self):
        """F9: 智慧校正"""
        try:
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            x, y = point.x, point.y
            target = self.calib_target_var.get()
            
            if self.calibration_step == 0:
                if target == "HP":
                    self.hp_y.set(y)
                    self.hp_x_min.set(x)
                else:
                    self.mp_y.set(y)
                    self.mp_x_min.set(x)
                
                msg = f"✅ [{target}] 起點已鎖定！請移到 100% 處再按 F9"
                print(msg)
                self.status_var.set(msg)
                self.calibration_step = 1
                
            elif self.calibration_step == 1:
                if target == "HP":
                    self.hp_x_max.set(x)
                else:
                    self.mp_x_max.set(x)
                
                msg = f"🎉 [{target}] 設定完成！請記得設定另一個，或按 F7 開始"
                print(msg)
                self.status_var.set(msg)
                self.calibration_step = 0

        except Exception as e:
            print(f"Debug Error: {e}")

    def toggle_start(self):
        if self.is_running.is_set():
            self.stop()
        else:
            self.start()

    def start(self):
        if not self.is_running.is_set():
            self.is_running.set()
            self.start_btn.config(text="停止偵測 (F7)")
            self.status_var.set("⚡ 雙開模式運行中...")
            self.status_label.config(foreground="green")
            self.worker_thread = threading.Thread(target=self._loop, daemon=True)
            self.worker_thread.start()

    def stop(self):
        if self.is_running.is_set():
            self.is_running.clear()
            self.start_btn.config(text="開始偵測 (F7)")
            self.status_var.set("🔴 已停止")
            self.status_label.config(foreground="red")

    def _loop(self):
        print("--- 監控開始 ---")
        while self.is_running.is_set():
            try:
                now = time.time()
                
                # --- 1. 檢測 HP ---
                if now - self.last_hp_time > self.trigger_cooldown:
                    hp_y = self.hp_y.get()
                    if hp_y != 0: 
                        hp_x = int(self.hp_x_min.get() + (self.hp_x_max.get() - self.hp_x_min.get()) * (self.hp_threshold.get() / 100.0))
                        rgb = self._get_rgb_at(hp_x, hp_y)
                        if rgb and rgb[2] >= 200:
                            print(f"[HP觸發] 血量不足! 按 {self.hp_key.get()}")
                            keyboard.send(self.hp_key.get())
                            self.last_hp_time = time.time()

                # --- 2. 檢測 MP ---
                if now - self.last_mp_time > self.trigger_cooldown:
                    mp_y = self.mp_y.get()
                    if mp_y != 0:
                        mp_x = int(self.mp_x_min.get() + (self.mp_x_max.get() - self.mp_x_min.get()) * (self.mp_threshold.get() / 100.0))
                        rgb = self._get_rgb_at(mp_x, mp_y)
                        if rgb and rgb[0] >= 200:
                            print(f"[MP觸發] 魔力不足! 按 {self.mp_key.get()}")
                            keyboard.send(self.mp_key.get())
                            self.last_mp_time = time.time()

                time.sleep(0.05)
            except Exception as e:
                print(f"Loop Error: {e}")
                time.sleep(1)

    @staticmethod
    def _get_rgb_at(x, y):
        hdc = GetDC(None)
        if not hdc: return None
        try:
            pixel = GetPixel(hdc, x, y)
            if pixel == 0xFFFFFFFF: return None
            r = pixel & 0xFF
            g = (pixel >> 8) & 0xFF
            b = (pixel >> 16) & 0xFF
            return (r, g, b)
        finally:
            ReleaseDC(None, hdc)

if __name__ == "__main__":
    app = DualAutoPotApp()
    app.root.mainloop()