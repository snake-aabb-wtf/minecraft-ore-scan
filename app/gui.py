import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import sys
import os
import webbrowser
from pathlib import Path

from .constants import (
    ORE_OPTIONS,
    DIMENSIONS,
    VERSION_TYPE_OPTIONS,
    ADOPTIUM_RELEASES_URL,
    RCON_PASSWORD,
    RCON_PORT,
    DIMENSION_ORES,
    DIMENSION_DEFAULT_ORES,
)
from .rcon import RconClient
from .installer import (
    fetch_versions,
    download_server,
    update_server_properties,
    find_installed_servers,
    get_server_java_requirement,
    uninstall_server,
)
from .java_runtime import find_java_runtimes, select_java_runtime, format_java_runtimes
from .world import start_server, pregenerate_chunks, get_region_dir, scan_all_regions
from .excel import export_to_excel


class JavaCompatibilityError(RuntimeError):
    pass


class OreScanGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Minecraft 矿物扫描工具")
        self.root.geometry("920x780")
        self.running = False
        self.worker = None
        self.server_process = None
        self.manifest_data = None

        if getattr(sys, 'frozen', False):
            self.app_dir = Path(os.path.dirname(sys.executable))
        else:
            self.app_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        self.minecraft_dir = self.app_dir / "Minecraft"
        self.current_server_dir = None

        self.container = ttk.Frame(self.root, padding=10)
        self.container.pack(fill=tk.BOTH, expand=True)

        self.frames = {}
        self._check_minecraft_dir()

    def _clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def _check_minecraft_dir(self):
        self.minecraft_dir.mkdir(exist_ok=True)
        installed = find_installed_servers(self.minecraft_dir)
        if installed:
            self.current_server_dir = installed[0]
            self._show_main_scan_page()
        else:
            self._show_install_page()

    def _show_install_page(self):
        self._clear_container()
        frame = ttk.Frame(self.container)
        frame.pack(fill=tk.BOTH, expand=True)
        self.frames["install"] = frame

        title_label = ttk.Label(frame, text="Minecraft 服务端安装向导", font=("Microsoft YaHei UI", 16, "bold"))
        title_label.pack(pady=(0, 10))

        ttk.Label(frame, text=f"安装目录: {self.minecraft_dir}", foreground="gray").pack(pady=(0, 10))

        self.install_status_label = ttk.Label(frame, text="正在获取版本列表...", font=("Microsoft YaHei UI", 10))
        self.install_status_label.pack(pady=20)

        self.install_log_text = scrolledtext.ScrolledText(frame, height=8, wrap=tk.WORD, font=("Consolas", 9))
        self.install_log_text.pack(fill=tk.X, pady=(0, 10))
        self._install_log_sync("欢迎使用矿物扫描工具！需要先安装 Minecraft Vanilla Server。")
        self._install_log_sync("正在从 Mojang 服务器获取可用版本...")

        version_filter_frame = ttk.Frame(frame)
        version_filter_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(version_filter_frame, text="可用版本").pack(side=tk.LEFT)

        self.version_type_var = tk.StringVar()
        self.version_type_combo = ttk.Combobox(
            version_filter_frame,
            textvariable=self.version_type_var,
            values=[label for _, label in VERSION_TYPE_OPTIONS],
            state="readonly",
            width=20,
        )
        self.version_type_combo.current(0)
        self.version_type_combo.bind("<<ComboboxSelected>>", self._on_version_type_changed)
        self.version_type_combo.pack(side=tk.LEFT, padx=(8, 0))

        list_frame = ttk.LabelFrame(frame, text="版本列表", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("version", "type", "release_date")
        self.version_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12, selectmode="browse")
        self.version_tree.heading("version", text="版本号")
        self.version_tree.heading("type", text="类型")
        self.version_tree.heading("release_date", text="发布日期")
        self.version_tree.column("version", width=150)
        self.version_tree.column("type", width=100)
        self.version_tree.column("release_date", width=200)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.version_tree.yview)
        self.version_tree.configure(yscrollcommand=scrollbar.set)
        self.version_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.refresh_btn = ttk.Button(btn_frame, text="刷新版本列表", command=self._load_versions)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)

        self.install_btn = ttk.Button(btn_frame, text="安装选中版本", command=self._start_install, state=tk.DISABLED)
        self.install_btn.pack(side=tk.LEFT, padx=5)

        if find_installed_servers(self.minecraft_dir):
            ttk.Button(btn_frame, text="管理已有", command=self._show_server_manager).pack(side=tk.RIGHT, padx=5)

        self._install_progress = ttk.Progressbar(frame, mode='determinate')
        self._install_progress.pack(fill=tk.X, pady=(10, 0))

        self._load_versions()

    def _install_log(self, msg):
        self.root.after(0, lambda: self._install_log_sync(msg))

    def _install_log_sync(self, msg):
        if hasattr(self, 'install_log_text') and self.install_log_text.winfo_exists():
            self.install_log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.install_log_text.see(tk.END)

    def _load_versions(self):
        self.refresh_btn.config(state=tk.DISABLED)
        self.install_btn.config(state=tk.DISABLED)
        self.version_type_combo.config(state="disabled")
        self.version_tree.delete(*self.version_tree.get_children())
        if hasattr(self, 'install_status_label'):
            self.install_status_label.config(text="正在获取版本列表...")
        version_type = self._get_selected_version_type()
        threading.Thread(target=self._fetch_versions, args=(version_type,), daemon=True).start()

    def _get_selected_version_type(self):
        selected_label = self.version_type_var.get()
        return next(
            (version_type for version_type, label in VERSION_TYPE_OPTIONS if label == selected_label),
            VERSION_TYPE_OPTIONS[0][0],
        )

    def _get_version_type_label(self, version_type):
        return next(
            (label for option_type, label in VERSION_TYPE_OPTIONS if option_type == version_type),
            version_type,
        )

    def _on_version_type_changed(self, event=None):
        self._load_versions()

    def _fetch_versions(self, version_type):
        try:
            self._install_log("正在连接 Mojang 版本服务器...")
            manifest_data, versions = fetch_versions(version_type)
            type_label = self._get_version_type_label(version_type)
            self._install_log(f"获取成功，共 {len(versions)} 个{type_label}版本")

            def update_version_list():
                self.manifest_data = manifest_data
                for v in versions:
                    self.version_tree.insert("", tk.END, values=(v["id"], v["type"], v["releaseTime"]))
                self.install_btn.config(state=tk.NORMAL if versions else tk.DISABLED)
                self.install_status_label.config(
                    text=f"已加载 {len(versions)} 个{type_label}版本"
                )

            self.root.after(0, update_version_list)
        except Exception as e:
            self._install_log(f"获取版本列表失败: {e}")
            error_message = str(e)
            self.root.after(0, lambda: messagebox.showerror("错误", f"获取版本列表失败: {error_message}"))
        finally:
            self.root.after(0, self._finish_version_load)

    def _finish_version_load(self):
        self.refresh_btn.config(state=tk.NORMAL)
        self.version_type_combo.config(state="readonly")

    def _start_install(self):
        sel = self.version_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选择一个版本")
            return
        item = self.version_tree.item(sel[0])
        version_id = item["values"][0]
        if not messagebox.askyesno("确认安装", f"即将安装 Minecraft Server {version_id}\n安装位置: {self.minecraft_dir / version_id}\n是否继续？"):
            return
        self.install_btn.config(state=tk.DISABLED)
        self.refresh_btn.config(state=tk.DISABLED)
        self.running = True
        threading.Thread(target=self._do_install, args=(version_id,), daemon=True).start()

    def _do_install(self, version_id):
        try:
            server_dir = self.minecraft_dir / version_id
            self._install_log(f"开始安装版本 {version_id}...")
            self.root.after(0, lambda: self.install_status_label.config(text=f"正在下载 Minecraft Server {version_id}..."))

            def progress(pct, downloaded, total):
                self.root.after(0, lambda: self._install_progress.configure(value=pct))
                if pct % 25 == 0 and pct > 0:
                    mb = downloaded / 1024 / 1024
                    total_mb = total / 1024 / 1024
                    self._install_log(f"下载进度: {pct}% ({mb:.1f}/{total_mb:.1f} MB)")

            size = download_server(server_dir, version_id, self.manifest_data, progress_callback=progress)
            self._install_log(f"server.jar 下载完成 ({size / 1024 / 1024:.1f} MB)")
            self._install_log("=" * 50)
            self._install_log("安装完成！正在进入主界面...")
            self.root.after(0, lambda: self.install_status_label.config(text="安装完成！"))
            time.sleep(2)
            self.current_server_dir = server_dir
            self.running = False
            self.root.after(0, self._show_main_scan_page)

        except Exception as e:
            self._install_log(f"安装失败: {e}")
            import traceback
            self._install_log(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("安装失败", str(e)))
            self.root.after(0, lambda: self.install_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.refresh_btn.config(state=tk.NORMAL))
            self.running = False

    def _show_main_scan_page(self):
        self._clear_container()
        frame = ttk.Frame(self.container)
        frame.pack(fill=tk.BOTH, expand=True)
        self.frames["main"] = frame

        top_frame = ttk.Frame(frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        server_info_frame = ttk.Frame(top_frame)
        server_info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            server_info_frame,
            text=f"当前服务端: {self.current_server_dir.name}",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor=tk.W)
        java_status_frame = ttk.Frame(server_info_frame)
        java_status_frame.pack(anchor=tk.W, pady=(2, 0))
        self.java_status_label = ttk.Label(
            java_status_frame,
            text="Java: 正在检测 Mojang 要求和本机运行时...",
            foreground="gray",
        )
        self.java_status_label.pack(side=tk.LEFT)
        self.install_java_btn = ttk.Button(
            java_status_frame,
            command=self._open_adoptium_releases,
        )
        ttk.Button(top_frame, text="管理服务端", command=self._show_server_manager).pack(side=tk.RIGHT)

        config_frame = ttk.LabelFrame(frame, text="扫描配置", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))

        row = 0

        ttk.Label(config_frame, text="世界种子:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.seed_var = tk.StringVar(value="")
        ttk.Entry(config_frame, textvariable=self.seed_var, width=30).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="(留空则随机生成)", foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        ttk.Label(config_frame, text="目标维度:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.dim_var = tk.StringVar(value=DIMENSIONS[0][0])
        self.dim_combo = ttk.Combobox(config_frame, textvariable=self.dim_var, width=25, state="readonly")
        self.dim_combo['values'] = [f"{id} ({name})" for id, name in DIMENSIONS]
        self.dim_combo.current(0)
        self.dim_combo.grid(row=row, column=1, sticky=tk.W, pady=5)
        self.dim_combo.bind("<<ComboboxSelected>>", self._on_dimension_changed)
        row += 1

        ttk.Label(config_frame, text="区块半径:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.radius_var = tk.IntVar(value=50)
        radius_spin = ttk.Spinbox(config_frame, from_=1, to=500, textvariable=self.radius_var, width=10)
        radius_spin.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="(半径50 = 100×100区块)", foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        ttk.Label(config_frame, text="原点坐标 (X,Y,Z):").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.origin_var = tk.StringVar(value="0,64,0")
        ttk.Entry(config_frame, textvariable=self.origin_var, width=20).grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="(距离计算参考点)", foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        ttk.Label(config_frame, text="输出 Excel:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.output_var = tk.StringVar(value="minerals.xlsx")
        ttk.Entry(config_frame, textvariable=self.output_var, width=30).grid(row=row, column=1, sticky=tk.W, pady=5)
        row += 1

        ttk.Label(config_frame, text="磁盘空间阈值:").grid(row=row, column=0, sticky=tk.W, pady=5)
        self.disk_free_var = tk.StringVar(value="8")
        disk_entry = ttk.Entry(config_frame, textvariable=self.disk_free_var, width=10)
        disk_entry.grid(row=row, column=1, sticky=tk.W, pady=5)
        ttk.Label(config_frame, text="GB (留空=不限制)", foreground="gray").grid(row=row, column=2, sticky=tk.W, padx=5, pady=5)
        row += 1

        self.ore_label_row = row
        ttk.Label(config_frame, text="选择矿物:").grid(row=row, column=0, sticky=tk.NW, pady=5)
        self.ore_frame = ttk.Frame(config_frame)
        self.ore_frame.grid(row=row, column=1, columnspan=3, sticky=tk.W, pady=5)
        self.ore_vars = {}
        self._populate_ores("minecraft:overworld")
        row += 1

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        self.start_btn = ttk.Button(btn_frame, text="开始扫描", command=self._start_scan)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_scan, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.scan_progress = ttk.Progressbar(frame, mode='indeterminate')
        self.scan_progress.pack(fill=tk.X, pady=(0, 10))

        log_frame = ttk.LabelFrame(frame, text="运行日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self._log_sync(f"服务端目录: {self.current_server_dir}")
        self._log_sync("准备就绪，请配置参数后点击「开始扫描」")
        self._refresh_java_status()

    def _resolve_java_runtime(self, server_dir):
        requirement = get_server_java_requirement(server_dir)
        runtimes = find_java_runtimes()
        selected_runtime = select_java_runtime(requirement.major_version, runtimes)
        return requirement, selected_runtime, runtimes

    def _java_mismatch_message(self, requirement, runtimes):
        component_text = f" ({requirement.component})" if requirement.component else ""
        detected = format_java_runtimes(runtimes)
        return (
            f"服务端 {requirement.version_id} 需要 Java {requirement.major_version}{component_text}，"
            f"但未检测到匹配的 Java 运行时。\n\n已检测到：{detected}\n\n"
            f"请安装 Java {requirement.major_version} JDK 或 JRE 后重试。"
        )

    def _open_adoptium_releases(self):
        webbrowser.open(ADOPTIUM_RELEASES_URL, new=2)

    def _set_install_java_button(self, required_major_version=None):
        button = getattr(self, "install_java_btn", None)
        if not button or not button.winfo_exists():
            return

        if required_major_version is None:
            button.pack_forget()
            return

        button.config(text=f"安装 Java {required_major_version}")
        if not button.winfo_manager():
            button.pack(side=tk.LEFT, padx=(8, 0))

    def _refresh_java_status(self):
        server_dir = self.current_server_dir
        if not server_dir:
            return

        def check_java_status():
            try:
                requirement, selected_runtime, _ = self._resolve_java_runtime(server_dir)
                if selected_runtime:
                    text = (
                        f"Java: 服务端需要 Java {requirement.major_version}，"
                        f"将使用 Java {selected_runtime.version_text}"
                    )
                    foreground = "dark green"
                    required_major_version = None
                else:
                    text = (
                        f"Java 不匹配: 服务端需要 Java {requirement.major_version}，"
                        "不会使用其他 Java 版本"
                    )
                    foreground = "firebrick"
                    required_major_version = requirement.major_version
            except Exception as e:
                text = f"Java 警告: 无法确认服务端 Java 要求: {e}"
                foreground = "firebrick"
                required_major_version = None

            def update_status():
                if self.current_server_dir != server_dir:
                    return
                label = getattr(self, "java_status_label", None)
                if label and label.winfo_exists():
                    label.config(text=text, foreground=foreground)
                self._set_install_java_button(required_major_version)

            self.root.after(0, update_status)

        threading.Thread(target=check_java_status, daemon=True).start()

    def _show_server_manager(self):
        if self.running:
            messagebox.showwarning("无法管理服务端", "扫描正在运行，请先停止扫描后再卸载服务端。")
            return

        servers = find_installed_servers(self.minecraft_dir)
        win = tk.Toplevel(self.root)
        win.title("服务端管理")
        win.geometry("500x400")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="已安装的服务端:", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W, padx=10, pady=10)

        list_frame = ttk.Frame(win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        lb = tk.Listbox(list_frame, font=("Consolas", 10))
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.configure(yscrollcommand=sb.set)

        for i, s in enumerate(servers):
            lb.insert(tk.END, s.name)
            if s == self.current_server_dir:
                lb.selection_set(i)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        def use_selected():
            sel = lb.curselection()
            if sel:
                self.current_server_dir = servers[sel[0]]
                win.destroy()
                self._show_main_scan_page()

        def install_new():
            win.destroy()
            self._show_install_page()

        def uninstall_selected():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("提示", "请先选择要卸载的服务端")
                return

            server_dir = servers[sel[0]]
            if not messagebox.askyesno(
                "确认卸载",
                f"即将卸载服务端 {server_dir.name}\n"
                f"将删除整个目录及其中的世界、备份和配置：\n{server_dir}\n\n"
                "此操作不可恢复，是否继续？",
            ):
                return

            try:
                uninstall_server(server_dir, self.minecraft_dir)
            except Exception as e:
                messagebox.showerror("卸载失败", f"卸载服务端失败: {e}")
                return

            remaining = find_installed_servers(self.minecraft_dir)
            if server_dir == self.current_server_dir:
                if remaining:
                    self.current_server_dir = remaining[0]
                    win.destroy()
                    self._show_main_scan_page()
                else:
                    self.current_server_dir = None
                    win.destroy()
                    self._show_install_page()
            else:
                win.destroy()

        ttk.Button(btn_frame, text="使用选中", command=use_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="卸载选中", command=uninstall_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="安装新版本", command=install_new).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=win.destroy).pack(side=tk.RIGHT, padx=5)

    def _log(self, msg):
        self.root.after(0, lambda: self._log_sync(msg))

    def _log_sync(self, msg):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see(tk.END)

    def _populate_ores(self, dimension_id):
        for widget in self.ore_frame.winfo_children():
            widget.destroy()
        self.ore_vars = {}
        ores = DIMENSION_ORES.get(dimension_id, [])
        default_ores = DIMENSION_DEFAULT_ORES.get(dimension_id, set())
        if not ores:
            ttk.Label(self.ore_frame, text="(该维度没有可用的矿物)", foreground="gray").grid(row=0, column=0, sticky=tk.W, pady=5)
            return
        cols = min(5, max(1, len(ores)))
        for i, (ore_id, ore_name) in enumerate(ores):
            var = tk.BooleanVar(value=(ore_id in default_ores))
            self.ore_vars[ore_id] = var
            ttk.Checkbutton(self.ore_frame, text=ore_name, variable=var).grid(
                row=i // cols, column=i % cols, sticky=tk.W, padx=8, pady=2)

    def _on_dimension_changed(self, event=None):
        dim_text = self.dim_var.get()
        dim_id = dim_text.split(" ")[0]
        self._populate_ores(dim_id)
        dim_name = next((name for id, name in DIMENSIONS if id == dim_id), dim_id)
        self._log_sync(f"已切换到维度: {dim_name}，矿物列表已更新")

    def _get_selected_config(self):
        ores = []
        dim_text = self.dim_var.get()
        dim_id = dim_text.split(" ")[0]
        for ore_id, var in self.ore_vars.items():
            if var.get():
                ores.append(ore_id)
        return ores, dim_id

    def _start_scan(self):
        if self.running:
            return
        ores, dim_id = self._get_selected_config()
        if not ores:
            messagebox.showwarning("警告", "请至少选择一种矿物！")
            return
        self.running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.scan_progress.start(10)

        origin_parts = [int(p.strip()) for p in self.origin_var.get().strip().split(",")]

        disk_free_text = self.disk_free_var.get().strip()
        min_free_gb = None
        if disk_free_text:
            try:
                min_free_gb = float(disk_free_text)
                if min_free_gb <= 0:
                    min_free_gb = None
            except ValueError:
                messagebox.showwarning("警告", "磁盘空间阈值必须是数字！")
                self.start_btn.config(state=tk.NORMAL)
                self.stop_btn.config(state=tk.DISABLED)
                self.scan_progress.stop()
                self.running = False
                return

        config = {
            "seed": self.seed_var.get().strip(),
            "dimension": dim_id,
            "radius": self.radius_var.get(),
            "ox": origin_parts[0],
            "oy": origin_parts[1],
            "oz": origin_parts[2],
            "output": self.output_var.get().strip(),
            "ores": ores,
            "server_dir": self.current_server_dir,
            "min_free_gb": min_free_gb,
        }

        self.worker = threading.Thread(target=self._run_pipeline, args=(config,), daemon=True)
        self.worker.start()

    def _stop_scan(self):
        if not self.running:
            return
        self.running = False
        self._log("正在停止... (等待当前操作完成)")
        self.stop_btn.config(state=tk.DISABLED)

        def graceful_shutdown():
            time.sleep(2)
            if self.server_process:
                try:
                    self._log("尝试优雅停止服务器...")
                    try:
                        rcon = RconClient("127.0.0.1", RCON_PORT, RCON_PASSWORD, timeout=5)
                        rcon.command("stop", retries=0)
                        rcon.close()
                        self._log("已发送 stop 命令，等待服务器关闭...")
                        time.sleep(10)
                    except:
                        pass
                    if self.server_process and self.server_process.poll() is None:
                        self._log("强制终止服务器进程...")
                        try:
                            self.server_process.terminate()
                            time.sleep(5)
                            if self.server_process.poll() is None:
                                self.server_process.kill()
                        except:
                            pass
                except:
                    pass

        threading.Thread(target=graceful_shutdown, daemon=True).start()

    def _run_pipeline(self, config):
        original_cwd = os.getcwd()
        output_dir = self.app_dir
        try:
            server_dir = config["server_dir"]
            self._log("检查 Mojang Java 运行时要求...")
            try:
                requirement, java_runtime, runtimes = self._resolve_java_runtime(server_dir)
            except Exception as e:
                raise JavaCompatibilityError(f"无法确认服务端 Java 要求: {e}") from e

            if not java_runtime:
                raise JavaCompatibilityError(self._java_mismatch_message(requirement, runtimes))

            self._log(
                f"服务端 {requirement.version_id} 需要 Java {requirement.major_version}，"
                f"将使用 Java {java_runtime.version_text}: {java_runtime.executable}"
            )
            self.root.after(0, self._refresh_java_status)
            os.chdir(server_dir)
            self._log(f"服务端工作目录: {server_dir}")
            self._log(f"Excel 输出目录: {output_dir}")

            server_jar = server_dir / "server.jar"
            if not server_jar.exists():
                raise RuntimeError("server.jar 不存在，请重新安装")

            self._log("配置服务器属性...")
            update_server_properties(server_dir / "server.properties", config["seed"])

            world_dir = server_dir / "world"
            seed = config["seed"]
            if world_dir.exists():
                if seed:
                    backup_name = f"world_backup_{int(time.time())}"
                    self._log(f"检测到已有世界目录，备份为 {backup_name}...")
                    world_dir.rename(server_dir / backup_name)
                else:
                    self._log("检测到已有世界，将复用该世界（未指定新种子）")

            self._log("启动 Minecraft 服务器...")
            self.server_process = start_server(
                server_dir,
                java_executable=java_runtime.executable,
                log_callback=lambda l: self._log(f"[Server] {l}"),
            )

            self._log("等待服务器启动（约30-120秒）...")
            rcon = None
            ready_checks = 0
            for i in range(180):
                if not self.running:
                    return
                time.sleep(3)
                try:
                    test_rcon = RconClient("127.0.0.1", RCON_PORT, RCON_PASSWORD, timeout=15)
                    resp = test_rcon.command("seed", retries=0)
                    test_rcon.close()
                    ready_checks += 1
                    if ready_checks >= 2:
                        rcon = RconClient("127.0.0.1", RCON_PORT, RCON_PASSWORD, timeout=120)
                        self._log(f"✓ 服务器就绪！种子信息: {resp.strip()[:80]}")
                        break
                    else:
                        self._log("  RCON 已连通，等待服务器完全加载...")
                        time.sleep(5)
                except Exception:
                    ready_checks = 0
                    if i % 10 == 0:
                        self._log(f"  等待中... ({i*3}s)")
            if not rcon:
                raise RuntimeError("服务器启动超时，请检查 Java 是否正确安装")

            self._log("等待服务器稳定（额外等待15秒）...")
            time.sleep(15)

            cancelled = False
            try:
                min_chunk = -config["radius"]
                max_chunk = config["radius"] - 1
                total_chunks = (max_chunk - min_chunk + 1) ** 2
                self._log(f"开始预生成区块: {min_chunk}..{max_chunk} (共 {total_chunks} 个区块)")
                region_dir = get_region_dir(world_dir, config["dimension"])
                ok = pregenerate_chunks(
                    rcon, config["dimension"], min_chunk, max_chunk, region_dir,
                    running_check=lambda: self.running,
                    log_callback=self._log,
                    min_free_gb=config["min_free_gb"]
                )
                if not ok or not self.running:
                    cancelled = True
                    self._log("操作已取消。")
                else:
                    self._log("区块生成完成，保存世界...")
                    try:
                        rcon.command("save-all flush", retries=1)
                        time.sleep(3)
                        rcon.command("stop", retries=1)
                        self._log("服务器已发送停止命令...")
                        time.sleep(8)
                    except Exception as e:
                        self._log(f"发送 RCON 命令时出错 (可能服务器已停止): {e}")
            finally:
                try:
                    rcon.close()
                except:
                    pass

            if self.server_process:
                try:
                    self.server_process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    try:
                        self.server_process.kill()
                    except:
                        pass
                self.server_process = None

            if cancelled or not self.running:
                self._log("操作已被用户取消。")
                return

            self._log("=" * 50)
            self._log("开始扫描矿物方块...")
            positions = scan_all_regions(
                region_dir, min_chunk, max_chunk, set(config["ores"]),
                running_check=lambda: self.running,
                log_callback=self._log
            )
            self._log(f"共找到 {len(positions)} 个矿物方块")

            output_name = config["output"]
            output_path = output_dir / output_name
            self._log(f"共找到 {len(positions)} 个矿物方块，正在排序...")
            rows_count, sheets_count = export_to_excel(
                positions, output_path,
                config["ox"], config["oy"], config["oz"],
                log_callback=self._log
            )

            self._log("=" * 50)
            self._log(f"✓ 全部完成！{rows_count} 条数据写入 {sheets_count} 个工作表。")
            self.root.after(0, lambda: messagebox.showinfo("完成", f"扫描完成！\n找到 {rows_count} 个矿物\n结果已保存到: {output_path.resolve()}"))

        except JavaCompatibilityError as e:
            error_message = str(e)
            self._log(f"✗ Java 警告: {error_message}")
            self.root.after(
                0,
                lambda: messagebox.showwarning("Java 版本警告", error_message),
            )
        except Exception as e:
            error_message = str(e)
            self._log(f"✗ 错误: {error_message}")
            import traceback
            self._log(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("错误", error_message))
        finally:
            os.chdir(original_cwd)
            self.running = False
            if self.server_process:
                try:
                    self.server_process.kill()
                except:
                    pass
                self.server_process = None
            self.root.after(0, self._reset_scan_ui)

    def _reset_scan_ui(self):
        self.scan_progress.stop()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
