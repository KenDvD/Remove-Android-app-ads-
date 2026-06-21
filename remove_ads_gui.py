import json
import os
import queue
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from remove_ads import process_apk, detect_ad_sdks, _PATTERNS, reload_patterns

# 可选拖拽支持
try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

CONFIG_PATH = Path.home() / ".apk_cleaner_config.json"


def _load_config():
    """加载持久化配置。"""
    defaults = {
        "appearance_mode": "Dark",
        "last_apk_path": "",
        "last_out_dir": "",
        "opt_manifest": True,
        "opt_assets": True,
        "opt_so": False,
        "opt_res": False,
        "opt_sign": True,
        "opt_stub": False,
    }
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
    except (json.JSONDecodeError, IOError):
        pass
    return defaults


def _save_config(config_dict):
    """保存配置到磁盘。"""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class ApkModApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self._config = _load_config()
        ctk.set_appearance_mode(self._config.get("appearance_mode", "Dark"))
        ctk.set_default_color_theme("blue")

        self.title("APK 纯净大师 v2.0 - 去广告封装工具")
        self.geometry("900x720")
        self.resizable(True, True)
        self.minsize(800, 600)

        # 尝试恢复窗口位置
        saved_geo = self._config.get("window_geometry", "")
        if saved_geo:
            try:
                self.geometry(saved_geo)
            except Exception:
                pass

        self.apk_path_var = ctk.StringVar()
        self.out_path_var = ctk.StringVar()

        # 恢复上次路径
        last_apk = self._config.get("last_apk_path", "")
        last_out = self._config.get("last_out_dir", "")
        if last_apk and os.path.exists(last_apk):
            self.apk_path_var.set(os.path.dirname(last_apk))
        if last_out and os.path.exists(last_out):
            self.out_path_var.set(last_out)

        self.opt_manifest = ctk.BooleanVar(value=self._config.get("opt_manifest", True))
        self.opt_assets = ctk.BooleanVar(value=self._config.get("opt_assets", True))
        self.opt_so = ctk.BooleanVar(value=self._config.get("opt_so", False))
        self.opt_res = ctk.BooleanVar(value=self._config.get("opt_res", False))
        self.opt_smali = ctk.BooleanVar(value=self._config.get("opt_smali", False))
        self.opt_sign = ctk.BooleanVar(value=self._config.get("opt_sign", True))
        self.opt_stub = ctk.BooleanVar(value=self._config.get("opt_stub", False))

        self.log_queue = queue.Queue()
        self._cancel_event = None
        self._preview_thread = None
        self._detected_sdks = {}  # 缓存预扫描结果

        self.setup_ui()

        # 启动日志队列轮询
        self.after(100, self._poll_log_queue)

        # 拖拽支持
        if HAS_DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

        # 窗口关闭时保存配置
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """关闭窗口时保存配置。"""
        self._config.update({
            "appearance_mode": ctk.get_appearance_mode(),
            "window_geometry": self.geometry(),
            "last_apk_path": self.apk_path_var.get(),
            "last_out_dir": self.out_path_var.get(),
            "opt_manifest": self.opt_manifest.get(),
            "opt_assets": self.opt_assets.get(),
            "opt_so": self.opt_so.get(),
            "opt_res": self.opt_res.get(),
            "opt_smali": self.opt_smali.get(),
            "opt_sign": self.opt_sign.get(),
            "opt_stub": self.opt_stub.get(),
        })
        _save_config(self._config)
        self.destroy()

    def setup_ui(self):
        # === 文件选择区 ===
        frame_file = ctk.CTkFrame(self)
        frame_file.pack(pady=(15, 5), padx=20, fill="x")

        ctk.CTkLabel(frame_file, text="输入 APK:", width=75, anchor="e").grid(
            row=0, column=0, padx=10, pady=8)
        ctk.CTkEntry(frame_file, textvariable=self.apk_path_var, width=560,
                     state="readonly").grid(row=0, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkButton(frame_file, text="浏览...", width=80,
                      command=self.browse_apk).grid(row=0, column=2, padx=10, pady=8)

        ctk.CTkLabel(frame_file, text="输出目录:", width=75, anchor="e").grid(
            row=1, column=0, padx=10, pady=8)
        ctk.CTkEntry(frame_file, textvariable=self.out_path_var, width=560,
                     state="readonly").grid(row=1, column=1, padx=5, pady=8, sticky="ew")
        ctk.CTkButton(frame_file, text="浏览...", width=80,
                      command=self.browse_out).grid(row=1, column=2, padx=10, pady=8)

        frame_file.grid_columnconfigure(1, weight=1)

        # === 选项区 ===
        frame_opt = ctk.CTkFrame(self)
        frame_opt.pack(pady=5, padx=20, fill="x")

        ctk.CTkLabel(frame_opt, text="清理选项配置",
                     font=ctk.CTkFont(weight="bold", size=13)).pack(
            anchor="w", padx=15, pady=(10, 5))

        opt_layout = ctk.CTkFrame(frame_opt, fg_color="transparent")
        opt_layout.pack(fill="x", padx=15, pady=5)
        opt_layout.grid_columnconfigure((0, 1, 2), weight=1)

        row0 = ctk.CTkFrame(opt_layout, fg_color="transparent")
        row0.grid(row=0, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(row0, text="清理 AndroidManifest (组件与权限)",
                        variable=self.opt_manifest).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(row0, text="删除广告资源文件 (Assets)",
                        variable=self.opt_assets).pack(side="left", padx=20)

        row1 = ctk.CTkFrame(opt_layout, fg_color="transparent")
        row1.grid(row=1, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(row1, text="删除广告动态库 (.so) [⚠ 可能闪退]",
                        variable=self.opt_so, text_color="#FF6B6B").pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(row1, text="清理 Smali 广告代码 [⚠ 高风险]",
                        variable=self.opt_smali, text_color="#FF4444").pack(side="left", padx=20)

        row2 = ctk.CTkFrame(opt_layout, fg_color="transparent")
        row2.grid(row=2, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(row2, text="清理广告布局资源 (Res)",
                        variable=self.opt_res).pack(side="left", padx=(0, 20))
        ctk.CTkCheckBox(row2, text="生成防检测空桩 [Beta]",
                        variable=self.opt_stub, text_color="#FFA500").pack(side="left", padx=20)

        row3 = ctk.CTkFrame(opt_layout, fg_color="transparent")
        row3.grid(row=3, column=0, columnspan=3, sticky="ew", pady=3)
        ctk.CTkCheckBox(row3, text="自动签名 (需 uber-apk-signer.jar)",
                        variable=self.opt_sign).pack(side="left", padx=(0, 20))

        # === 预扫描状态区 ===
        frame_preview = ctk.CTkFrame(self, fg_color="transparent")
        frame_preview.pack(pady=(5, 0), padx=20, fill="x")

        self.lbl_preview = ctk.CTkLabel(
            frame_preview, text="选择 APK 文件后将自动预扫描检测广告 SDK...",
            font=ctk.CTkFont(size=11), text_color="#888888")
        self.lbl_preview.pack(anchor="w", padx=5)

        # === 进度条 ===
        self.progress_bar = ctk.CTkProgressBar(self, mode="determinate", height=20)
        self.progress_bar.pack(pady=(10, 0), padx=20, fill="x")
        self.progress_bar.set(0)

        # === 日志文本框 ===
        self.log_box = ctk.CTkTextbox(self, height=160,
                                      font=ctk.CTkFont(family="Consolas", size=12),
                                      state="disabled")
        self.log_box.pack(pady=(10, 15), padx=20, fill="both", expand=True)

        # === 按钮区 ===
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 20), padx=20, fill="x")

        self.btn_start = ctk.CTkButton(
            btn_frame, text="▶ 开始处理", height=42,
            font=ctk.CTkFont(weight="bold", size=14),
            command=self.start_processing)
        self.btn_start.pack(fill="x")

        self.btn_cancel = ctk.CTkButton(
            btn_frame, text="✕ 取消处理", height=42,
            fg_color="#8B0000", hover_color="#A00000",
            font=ctk.CTkFont(weight="bold", size=14),
            command=self.cancel_processing)

        patterns_src = _PATTERNS.get("loaded_from", "builtin")
        self.safe_log(f"系统就绪。模式数据库: {patterns_src}\n请选择一个 APK 文件开始...\n")

    def browse_apk(self):
        filepath = filedialog.askopenfilename(filetypes=[("APK Files", "*.apk")])
        if filepath:
            self.apk_path_var.set(filepath)
            if not self.out_path_var.get():
                self.out_path_var.set(os.path.dirname(filepath))
            self._run_preview_scan(filepath)

    def browse_out(self):
        dirpath = filedialog.askdirectory()
        if dirpath:
            self.out_path_var.set(dirpath)

    def _run_preview_scan(self, apk_path):
        """后台线程预扫描 APK 检测广告 SDK。"""
        self.lbl_preview.configure(text="正在预扫描检测广告 SDK...", text_color="#FFA500")
        self._detected_sdks = {}

        def _scan():
            try:
                # 尝试快速读取 manifest
                import zipfile
                manifest_bytes = None
                assets_list = []
                with zipfile.ZipFile(apk_path, "r") as zf:
                    try:
                        manifest_bytes = zf.read("AndroidManifest.xml")
                    except KeyError:
                        pass
                    for name in zf.namelist():
                        if name.startswith("assets/"):
                            assets_list.append(os.path.basename(name))

                if manifest_bytes:
                    manifest_str = manifest_bytes.decode("utf-8", errors="ignore").lower()
                    assets_str = " ".join(assets_list).lower()

                    sdks = _PATTERNS.get("sdks", [])
                    detected = {}
                    for sdk in sdks:
                        match_count = 0
                        for kw in sdk.get("keywords", []):
                            if kw.lower() in manifest_str:
                                match_count += 1
                            if kw.lower() in assets_str:
                                match_count += 1
                        if match_count > 0:
                            detected[sdk["name"]] = {
                                "vendor": sdk.get("vendor", "?"),
                                "matches": match_count,
                            }

                    self._detected_sdks = detected
                    self.log_queue.put(("preview", detected))
                else:
                    self.log_queue.put(("preview_error", "无法读取 AndroidManifest.xml"))
            except Exception as e:
                self.log_queue.put(("preview_error", str(e)))

        self._preview_thread = threading.Thread(target=_scan, daemon=True)
        self._preview_thread.start()

    def _update_preview_label(self, detected):
        """更新预扫描标签。"""
        if not detected:
            self.lbl_preview.configure(
                text="预扫描完成: 未检测到已知广告 SDK（可能为无广告应用或新型 SDK）",
                text_color="#888888")
            return

        lines = ["预扫描检测到以下广告 SDK:"]
        for name, info in sorted(detected.items(), key=lambda x: -x[1]["matches"]):
            lines.append(f"  • {name} ({info['vendor']}, {info['matches']} 处匹配)")
        self.lbl_preview.configure(text="\n".join(lines), text_color="#4CAF50",
                                   font=ctk.CTkFont(size=10))

    def safe_log(self, message):
        """线程安全：将日志消息放入队列。"""
        self.log_queue.put(("log", message))

    def on_progress(self, step, total, message):
        """进度回调：从工作线程调用。"""
        self.log_queue.put(("progress", step / total if total > 0 else 0))
        self.log_queue.put(("log", f"  [{step}/{total}] {message}"))

    def _poll_log_queue(self):
        """主线程定时轮询队列，安全更新 UI。"""
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple):
                    kind = item[0]
                    if kind == "progress":
                        self.progress_bar.set(item[1])
                    elif kind == "log":
                        self._write_log(item[1])
                    elif kind == "preview":
                        self._update_preview_label(item[1])
                    elif kind == "preview_error":
                        self.lbl_preview.configure(
                            text=f"预扫描跳过: {item[1]}（将在处理时详细检测）",
                            text_color="#888888")
                    elif kind == "result":
                        self._show_result_dialog(item[1])
                    elif kind == "error":
                        self._show_error(item[1])
                else:
                    self._write_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)

    def _write_log(self, message):
        """在主线程中安全地写入日志框。"""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", str(message) + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def set_ui_busy(self, busy):
        """切换处理中/空闲状态的按钮显示。"""
        if busy:
            self.btn_start.pack_forget()
            self.btn_cancel.configure(state="normal", text="✕ 取消处理")
            self.btn_cancel.pack(fill="x")
        else:
            self.btn_cancel.pack_forget()
            self.btn_start.pack(fill="x")

    def start_processing(self):
        apk_path = self.apk_path_var.get()

        if not apk_path or not os.path.isfile(apk_path):
            messagebox.showerror("错误", "请选择有效的 APK 文件！")
            return

        self.set_ui_busy(True)
        self._cancel_event = threading.Event()
        self.progress_bar.set(0)

        self.safe_log("=" * 50)
        self.safe_log(f"开始处理: {os.path.basename(apk_path)}")

        threading.Thread(target=self.process_task, args=(apk_path,), daemon=True).start()

    def cancel_processing(self):
        """带确认的取消操作。"""
        if not self._cancel_event or self._cancel_event.is_set():
            return

        confirm = messagebox.askyesno(
            "确认取消", "确定要取消当前处理吗？\n\n已完成的步骤将被保留，未完成的步骤会被中断。")
        if not confirm:
            return

        self._cancel_event.set()
        self.safe_log("\n[用户操作] 正在取消处理，请稍候...")
        self.btn_cancel.configure(state="disabled", text="取消中...")

    def process_task(self, apk_path):
        try:
            out_dir = self.out_path_var.get() or os.path.dirname(apk_path)
            base_name = os.path.basename(apk_path)
            if base_name.lower().endswith(".apk"):
                base_name = base_name[:-4]
            output_apk = os.path.join(out_dir, f"{base_name}_killad.apk")

            options = {
                "manifest": self.opt_manifest.get(),
                "assets": self.opt_assets.get(),
                "so": self.opt_so.get(),
                "res": self.opt_res.get(),
                "smali": self.opt_smali.get(),
                "sign": self.opt_sign.get(),
                "stub": self.opt_stub.get(),
            }

            result = process_apk(
                apk_path,
                output_apk=output_apk,
                options=options,
                log_callback=self.safe_log,
                progress_callback=self.on_progress,
                cancel_event=self._cancel_event,
            )

            self.log_queue.put(("result", result))

        except Exception as e:
            self.log_queue.put(("error", str(e)))
        finally:
            self.after(0, self._on_process_finished)

    def _on_process_finished(self):
        self.set_ui_busy(False)
        self._cancel_event = None

    def _show_result_dialog(self, result):
        """处理完成后的结果摘要弹窗（含 SDK 检测信息）。"""
        detected_sdks = result.get("detected_sdks", [])
        extra_rows = 1 if detected_sdks else 0
        dialog_height = 420 + min(len(detected_sdks) * 22, 200)

        dialog = ctk.CTkToplevel(self)
        dialog.title("处理完成")
        dialog.geometry(f"500x{dialog_height}")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.lift()
        dialog.focus_force()

        # 居中于父窗口
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="处理成功完成！",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#4CAF50",
        ).pack(pady=(25, 10))

        frame = ctk.CTkFrame(dialog, fg_color="transparent")
        frame.pack(padx=30, pady=5, fill="both", expand=True)

        orig_mb = result["original_size"] / (1024 * 1024)
        final_mb = result["final_size"] / (1024 * 1024)
        diff_mb = (result["original_size"] - result["final_size"]) / (1024 * 1024)
        diff_pct = (1 - result["final_size"] / result["original_size"]) * 100 if result["original_size"] > 0 else 0

        rows = [
            ("输出文件", os.path.basename(result["output_path"])),
            ("原始大小", f"{orig_mb:.1f} MB"),
            ("最终大小", f"{final_mb:.1f} MB"),
            ("缩减", f"{diff_mb:.1f} MB ({diff_pct:.1f}%)"),
        ]
        if result.get("manifest_removed"):
            rows.append(("Manifest 清理", f"{result['manifest_removed']} 个广告节点"))
        if result.get("assets_removed"):
            rows.append(("Assets 清理", f"{len(result['assets_removed'])} 个文件"))
        if result.get("so_removed"):
            rows.append((".so 清理", f"{len(result['so_removed'])} 个文件"))
        if result.get("res_removed"):
            rows.append(("Res 清理", f"{len(result['res_removed'])} 个文件"))
        if result.get("smali_removed"):
            rows.append(("Smali 清理", f"{len(result['smali_removed'])} 个类"))
        if result.get("stubs_generated"):
            rows.append(("防检测桩", f"{result['stubs_generated']} 个组件"))
        rows.append(("签名状态", "已签名 ✓" if result["signed"] else "未签名 ✗"))

        for i, (label, value) in enumerate(rows):
            lbl = ctk.CTkLabel(frame, text=f"{label}:", width=120, anchor="e",
                               font=ctk.CTkFont(weight="bold"))
            lbl.grid(row=i, column=0, padx=5, pady=3, sticky="e")
            val = ctk.CTkLabel(frame, text=value, width=250, anchor="w")
            val.grid(row=i, column=1, padx=5, pady=3, sticky="w")

        # SDK 检测结果
        if detected_sdks:
            row_offset = len(rows)
            sep = ctk.CTkLabel(frame, text="", height=5)
            sep.grid(row=row_offset, column=0, columnspan=2)
            row_offset += 1

            header = ctk.CTkLabel(frame, text="检测到的广告 SDK:", width=380, anchor="w",
                                  font=ctk.CTkFont(weight="bold", size=12),
                                  text_color="#FFA500")
            header.grid(row=row_offset, column=0, columnspan=2, padx=5, pady=3, sticky="w")
            row_offset += 1

            for sdk_info in detected_sdks[:10]:  # 最多显示 10 个
                sdk_text = f"  • {sdk_info['name']} ({sdk_info.get('vendor', '?')})"
                sdk_lbl = ctk.CTkLabel(frame, text=sdk_text, width=380, anchor="w",
                                       font=ctk.CTkFont(size=11))
                sdk_lbl.grid(row=row_offset, column=0, columnspan=2, padx=5, pady=1, sticky="w")
                row_offset += 1

            if len(detected_sdks) > 10:
                more = ctk.CTkLabel(frame, text=f"  ... 及其他 {len(detected_sdks) - 10} 个 SDK",
                                    width=380, anchor="w", text_color="#888888")
                more.grid(row=row_offset, column=0, columnspan=2, padx=5, pady=1, sticky="w")

        ctk.CTkButton(dialog, text="确定", width=120, height=38,
                      command=dialog.destroy).pack(pady=(15, 25))

    def _show_error(self, error_msg):
        """显示致命错误弹窗。"""
        self._write_log(f"\n[致命错误] {error_msg}")

        dialog = ctk.CTkToplevel(self)
        dialog.title("处理失败")
        dialog.geometry("500x250")
        dialog.resizable(False, False)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - 250) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="处理失败",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#FF6B6B").pack(pady=(25, 15))

        err_box = ctk.CTkTextbox(dialog, height=80, font=ctk.CTkFont(family="Consolas", size=11),
                                 wrap="word")
        err_box.pack(padx=30, pady=5, fill="both", expand=True)
        err_box.insert("1.0", error_msg)
        err_box.configure(state="disabled")

        ctk.CTkButton(dialog, text="确定", width=120, height=35,
                      command=dialog.destroy).pack(pady=(15, 20))

    def _on_drop(self, event):
        """拖放 APK 文件处理（支持多文件）。"""
        filepath = event.data.strip()
        if filepath.startswith("{") and filepath.endswith("}"):
            filepath = filepath[1:-1]

        # 处理多个拖放文件
        parts = filepath.split("} {") if "} {" in filepath else [filepath]
        apk_candidates = []
        for part in parts:
            part = part.strip("{}")
            if part.lower().endswith(".apk") and os.path.isfile(part):
                apk_candidates.append(part)

        if not apk_candidates:
            return

        # 取第一个作为主文件
        first = apk_candidates[0]
        self.apk_path_var.set(first)
        if not self.out_path_var.get():
            self.out_path_var.set(os.path.dirname(first))
        self.safe_log(f"已拖入文件: {os.path.basename(first)}")
        self._run_preview_scan(first)

        if len(apk_candidates) > 1:
            self.safe_log(f"  另有 {len(apk_candidates) - 1} 个文件，可逐个处理")


if __name__ == "__main__":
    app = ApkModApp()
    app.mainloop()
