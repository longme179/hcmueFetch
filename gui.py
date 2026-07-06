"""Tkinter GUI interface."""

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from core import (
    DEFAULT_CONFIG,
    DEFAULT_SEEN,
    load_config,
    render_report,
    run_digest,
    save_config,
)


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Tin tức Trường - Top N mới nhất")
        self.root.geometry("1100x700")
        self.queue = queue.Queue()
        self.sources = load_config(DEFAULT_CONFIG)
        self.current_items = []

        self.build_ui()
        self.root.after(100, self.process_queue)

    def build_ui(self):
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=5)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Left Panel
        left = ttk.Frame(main_pane, padding=5)
        main_pane.add(left, minsize=250)
        ttk.Label(left, text="Nguồn tin:").pack(anchor=tk.W)
        self.src_listbox = tk.Listbox(left, height=20)
        self.src_listbox.pack(fill=tk.BOTH, expand=True)
        self.refresh_source_list()

        btn_f = ttk.Frame(left)
        btn_f.pack(fill=tk.X, pady=5)
        ttk.Button(btn_f, text="Thêm", command=self.add_source).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )
        ttk.Button(btn_f, text="Xoá", command=self.remove_source).pack(
            side=tk.LEFT, expand=True, fill=tk.X
        )

        # Right Panel
        right = ttk.Frame(main_pane, padding=5)
        main_pane.add(right)

        ctrl = ttk.Frame(right)
        ctrl.pack(fill=tk.X, pady=5)

        ttk.Label(ctrl, text="Số bài (N):").pack(side=tk.LEFT)
        self.count_var = tk.IntVar(value=10)
        for n in (10, 20, 30):
            ttk.Radiobutton(ctrl, text=str(n), variable=self.count_var, value=n).pack(
                side=tk.LEFT, padx=2
            )
        ttk.Entry(ctrl, textvariable=self.count_var, width=5).pack(side=tk.LEFT, padx=5)

        self.mode_var = tk.StringVar(value="per-source")
        ttk.Radiobutton(
            ctrl, text="Riêng từng nguồn", variable=self.mode_var, value="per-source"
        ).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(
            ctrl, text="Gộp tất cả", variable=self.mode_var, value="combined"
        ).pack(side=tk.LEFT, padx=5)

        self.no_excerpt_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            ctrl, text="Không trích đoạn", variable=self.no_excerpt_var
        ).pack(side=tk.LEFT, padx=5)

        self.reset_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl, text="Reset đã xem", variable=self.reset_var).pack(
            side=tk.LEFT, padx=5
        )

        ttk.Button(ctrl, text="Lưu file", command=self.save_report).pack(
            side=tk.RIGHT, padx=5
        )
        self.scan_btn = ttk.Button(ctrl, text="Cập nhật", command=self.start_scan)
        self.scan_btn.pack(side=tk.RIGHT, padx=5)

        # Results Treeview
        tree_f = ttk.Frame(right)
        tree_f.pack(fill=tk.BOTH, expand=True)

        cols = ("source", "date", "new", "title", "action", "url")
        self.tree = ttk.Treeview(tree_f, columns=cols, show="headings")
        self.tree.heading("source", text="Nguồn")
        self.tree.heading("date", text="Ngày")
        self.tree.heading("new", text="Trạng thái")
        self.tree.heading("title", text="Tiêu đề")
        self.tree.heading("action", text="Truy cập")

        self.tree.column("source", width=120, anchor=tk.W, stretch=False)
        self.tree.column("date", width=120, anchor=tk.W, stretch=False)
        self.tree.column("new", width=80, anchor=tk.CENTER, stretch=False)
        self.tree.column("title", width=450, anchor=tk.W, stretch=True)
        self.tree.column("action", width=80, anchor=tk.CENTER, stretch=False)
        self.tree.column(
            "url", width=0, minwidth=0, stretch=False
        )  # Ẩn triệt để cột URL

        vsb = ttk.Scrollbar(tree_f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", self.on_double_click)

        # Log area
        log_f = ttk.Frame(right, height=120)
        log_f.pack(fill=tk.BOTH, pady=(5, 0))
        ttk.Label(log_f, text="Log:").pack(anchor=tk.W)
        self.log_text = tk.Text(log_f, height=6, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def log(self, msg):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def refresh_source_list(self):
        self.src_listbox.delete(0, tk.END)
        for s in self.sources:
            self.src_listbox.insert(tk.END, s.get("name", s["url"]))

    def add_source(self):
        win = tk.Toplevel(self.root)
        win.title("Thêm nguồn mới")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Tên nguồn:").pack(pady=5)
        name_e = ttk.Entry(win, width=50)
        name_e.pack(pady=5)
        ttk.Label(win, text="URL:").pack(pady=5)
        url_e = ttk.Entry(win, width=50)
        url_e.pack(pady=5)

        def save():
            n, u = name_e.get().strip(), url_e.get().strip()
            if n and u:
                self.sources.append({"name": n, "url": u})
                save_config(self.sources, DEFAULT_CONFIG)
                self.refresh_source_list()
                win.destroy()
            else:
                messagebox.showwarning(
                    "Thiếu thông tin", "Vui lòng nhập đủ tên và URL.", parent=win
                )

        ttk.Button(win, text="Lưu", command=save).pack(pady=10)

    def remove_source(self):
        sel = self.src_listbox.curselection()
        if sel:
            del self.sources[sel[0]]
            save_config(self.sources, DEFAULT_CONFIG)
            self.refresh_source_list()

    def start_scan(self):
        self.scan_btn.config(state=tk.DISABLED)
        self.tree.delete(*self.tree.get_children())
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        try:
            final_items, error_sources = run_digest(
                sources=self.sources,
                count=self.count_var.get(),
                mode=self.mode_var.get(),
                no_excerpt=self.no_excerpt_var.get(),
                reset_seen=self.reset_var.get(),
                seen_path=DEFAULT_SEEN,
                log_func=lambda msg: self.queue.put(("log", msg)),
            )
            self.queue.put(("done", (final_items, error_sources)))
        except Exception as e:
            self.queue.put(("error", str(e)))

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "log":
                    self.log(data)
                elif msg_type == "done":
                    self.display_results(data)
                    self.scan_btn.config(state=tk.NORMAL)
                elif msg_type == "error":
                    self.log(f"LỖI HỆ THỐNG: {data}")
                    self.scan_btn.config(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def display_results(self, data):
        final_items, error_sources = data
        self.current_items = final_items
        for it in final_items:
            mark = "[MỚI]" if it.is_new else ""
            self.tree.insert(
                "",
                tk.END,
                values=(
                    it.source_name,
                    it.date_str(),
                    mark,
                    it.title,
                    "[Link]",
                    it.link,
                ),
            )

        self.log(f"Hoàn tất: {len(final_items)} bài.")
        if error_sources:
            self.log("Có lỗi ở các nguồn:")
            for n, e in error_sources:
                self.log(f"  - {n}: {e}")

    def on_tree_click(self, event):
        if (
            self.tree.identify("region", event.x, event.y) == "cell"
            and self.tree.identify_column(event.x) == "#5"
        ):
            item_id = self.tree.identify_row(event.y)
            if item_id:
                url = self.tree.item(item_id, "values")[5]
                if url and str(url).startswith("http"):
                    webbrowser.open(url)

    def on_double_click(self, event):
        if (
            self.tree.identify("region", event.x, event.y) == "cell"
            and self.tree.identify_column(event.x) == "#4"
        ):
            item_id = self.tree.identify_row(event.y)
            if item_id:
                url = self.tree.item(item_id, "values")[5]
                if url and str(url).startswith("http"):
                    webbrowser.open(url)

    def save_report(self):
        if not self.current_items:
            messagebox.showwarning("Cảnh báo", "Chưa có kết quả để lưu.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("Text files", "*.txt")]
        )
        if path:
            render_report(
                self.current_items, self.count_var.get(), self.mode_var.get(), [], path
            )
            messagebox.showinfo("Thành công", f"Đã lưu báo cáo:\n{path}")


def launch_gui():
    root = tk.Tk()
    App(root)
    root.mainloop()
