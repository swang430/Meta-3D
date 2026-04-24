#!/usr/bin/env python3
"""
SCPI 仪表调试工具 (SCPI Debugger)

一个用于快速调试仪器网络连接和 SCPI 指令的独立 GUI 工具。
支持通过 TCP Socket (默认 5025 端口) 发送任意 SCPI 指令，并读取响应。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import socket
import threading
import time

class SCPIDebugger:
    def __init__(self, root):
        self.root = root
        self.root.title("SCPI 仪表调试工具")
        self.root.geometry("650x550")
        self.root.minsize(500, 400)
        
        # 内部状态
        self.history = []
        self.history_index = -1
        
        self._create_widgets()
        
    def _create_widgets(self):
        # 顶部配置区
        config_frame = ttk.LabelFrame(self.root, text="连接配置", padding="10")
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(config_frame, text="IP 地址:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.ip_var = tk.StringVar(value="192.168.100.21")
        self.ip_entry = ttk.Entry(config_frame, textvariable=self.ip_var, width=15)
        self.ip_entry.grid(row=0, column=1, sticky=tk.W, padx=5)
        
        ttk.Label(config_frame, text="端口:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.port_var = tk.IntVar(value=5025)
        self.port_entry = ttk.Entry(config_frame, textvariable=self.port_var, width=8)
        self.port_entry.grid(row=0, column=3, sticky=tk.W, padx=5)
        
        ttk.Label(config_frame, text="超时(秒):").grid(row=0, column=4, sticky=tk.W, padx=5)
        self.timeout_var = tk.DoubleVar(value=3.0)
        self.timeout_entry = ttk.Entry(config_frame, textvariable=self.timeout_var, width=5)
        self.timeout_entry.grid(row=0, column=5, sticky=tk.W, padx=5)
        
        # 快捷测试按钮
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=1, column=0, columnspan=6, pady=(10, 0), sticky=tk.W)
        
        ttk.Button(btn_frame, text="测试连接 (*IDN?)", command=lambda: self.send_command("*IDN?")).pack(side=tk.LEFT, padx=(5, 10))
        ttk.Button(btn_frame, text="查询错误 (SYST:ERR?)", command=lambda: self.send_command("SYST:ERR?")).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="清除状态 (*CLS)", command=lambda: self.send_command("*CLS")).pack(side=tk.LEFT, padx=10)
        
        # 命令发送区
        cmd_frame = ttk.LabelFrame(self.root, text="SCPI 指令发送", padding="10")
        cmd_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.cmd_var = tk.StringVar()
        self.cmd_entry = ttk.Entry(cmd_frame, textvariable=self.cmd_var, font=('Consolas', 11))
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.cmd_entry.bind('<Return>', lambda e: self.send_command())
        self.cmd_entry.bind('<Up>', self._on_up_arrow)
        self.cmd_entry.bind('<Down>', self._on_down_arrow)
        
        self.send_btn = ttk.Button(cmd_frame, text="发送 (Enter)", command=self.send_command)
        self.send_btn.pack(side=tk.RIGHT)
        
        # 响应显示区
        log_frame = ttk.LabelFrame(self.root, text="通信日志 (Rx/Tx)", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Consolas', 10), bg="#1e1e1e", fg="#d4d4d4")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 配置日志颜色标签
        self.log_text.tag_config('tx', foreground='#569cd6') # 蓝色
        self.log_text.tag_config('rx', foreground='#4ec9b0') # 绿色
        self.log_text.tag_config('err', foreground='#f44747') # 红色
        self.log_text.tag_config('info', foreground='#808080') # 灰色
        
        # 底部状态栏
        self.status_var = tk.StringVar(value="准备就绪。按上下方向键可浏览历史命令。")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.log_message("[INFO] 欢迎使用 SCPI 调试工具。", 'info')
        self.log_message("[INFO] 工具默认通过 TCP Socket 发送裸指令并追加换行符(\\n)。", 'info')

    def log_message(self, message, tag=None):
        self.log_text.config(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, message + "\n", tag)
        else:
            self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _on_up_arrow(self, event):
        if not self.history:
            return
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.cmd_var.set(self.history[-(self.history_index + 1)])

    def _on_down_arrow(self, event):
        if not self.history:
            return
        if self.history_index > 0:
            self.history_index -= 1
            self.cmd_var.set(self.history[-(self.history_index + 1)])
        elif self.history_index == 0:
            self.history_index = -1
            self.cmd_var.set("")

    def send_command(self, override_cmd=None):
        cmd = override_cmd if override_cmd is not None else self.cmd_var.get().strip()
        if not cmd:
            return
            
        ip = self.ip_var.get().strip()
        try:
            port = self.port_var.get()
            timeout = self.timeout_var.get()
        except ValueError:
            messagebox.showerror("输入错误", "端口或超时必须是有效的数字！")
            return
            
        if not ip:
            messagebox.showerror("输入错误", "IP地址不能为空！")
            return

        # 添加到历史记录
        if override_cmd is None:
            if not self.history or self.history[-1] != cmd:
                self.history.append(cmd)
            self.history_index = -1
            self.cmd_var.set("")

        self.send_btn.config(state=tk.DISABLED)
        self.status_var.set(f"正在发送命令到 {ip}:{port} ...")
        
        # 启动线程发送以避免阻塞 GUI
        threading.Thread(target=self._socket_worker, args=(ip, port, timeout, cmd), daemon=True).start()

    def _socket_worker(self, ip, port, timeout_sec, cmd):
        sock = None
        start_time = time.time()
        try:
            self.log_message(f"\n[TX] {cmd}", 'tx')
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_sec)
            sock.connect((ip, port))
            
            # 发送命令
            sock.sendall((cmd + "\n").encode('utf-8'))
            
            # 如果是查询命令，尝试读取响应
            if "?" in cmd:
                response = ""
                while True:
                    try:
                        chunk = sock.recv(4096).decode('utf-8', errors='replace')
                        if not chunk:
                            break
                        response += chunk
                        if "\n" in chunk:
                            break
                    except socket.timeout:
                        if not response:
                            raise
                        break
                
                response = response.strip()
                if response:
                    self.log_message(f"[RX] {response}", 'rx')
                else:
                    self.log_message("[ERR] 收到空响应 (对方已接受 TCP 连接但未返回数据)", 'err')
            else:
                self.log_message("[INFO] 命令已发送 (无返回预期)", 'info')
                
            latency = (time.time() - start_time) * 1000
            self.root.after(0, lambda: self.status_var.set(f"通信成功 ({latency:.0f}ms)"))
            
        except socket.timeout:
            self.log_message("[ERR] 操作超时 (Timeout)! 无法连接或仪表未在规定时间内响应。", 'err')
            self.root.after(0, lambda: self.status_var.set("通信超时"))
        except ConnectionRefusedError:
            self.log_message(f"[ERR] 连接被拒绝 (Connection Refused)。请检查 {ip} 的 {port} 端口是否开放。", 'err')
            self.root.after(0, lambda: self.status_var.set("连接被拒绝"))
        except OSError as e:
            if e.errno == 65: # No route to host
                self.log_message(f"[ERR] 无法路由到目标 (No route to host)。请检查网络连通性或 IP 是否正确。", 'err')
            else:
                self.log_message(f"[ERR] 套接字错误 (OS Error): {e}", 'err')
            self.root.after(0, lambda: self.status_var.set("网络错误"))
        except Exception as e:
            self.log_message(f"[ERR] 未知错误: {str(e)}", 'err')
            self.root.after(0, lambda: self.status_var.set("发生错误"))
        finally:
            if sock:
                try:
                    sock.close()
                except:
                    pass
            self.root.after(0, lambda: self.send_btn.config(state=tk.NORMAL))

if __name__ == "__main__":
    root = tk.Tk()
    app = SCPIDebugger(root)
    # macOS 使得界面不那么拥挤
    root.tk.call('tk', 'scaling', 1.5)
    root.mainloop()
