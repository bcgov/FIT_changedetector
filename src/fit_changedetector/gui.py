"""
Minimal cross-platform GUI wrapper for the FIT ChangeDetector CLI.

Requires: Python 3.9+ with tkinter (included in standard CPython builds).
The `changedetector` CLI must be installed and on PATH (pip install fit-changedetector).

Usage:
    python gui.py
"""

import os
import subprocess
import sys
import threading
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _browse_file(entry: tk.Entry, title: str = "Select file", save: bool = False) -> None:
    """Open a file-dialog and put the chosen path into *entry*."""
    if save:
        path = filedialog.asksaveasfilename(title=title)
    else:
        path = filedialog.askopenfilename(title=title)
    if path:
        entry.delete(0, tk.END)
        entry.insert(0, path)


def _list_layers(path: str) -> list:
    """Return layer names available in *path*, or [] on failure."""
    path = path.strip()
    if not path:
        return []
    try:
        import fiona
        return fiona.listlayers(path)
    except Exception:
        pass
    try:
        import pyogrio
        return [str(r[0]) for r in pyogrio.list_layers(path)]
    except Exception:
        return []


def _list_fields(path: str, layer: str = None) -> list:
    """Return attribute field names for *path*/*layer*, or [] on failure."""
    path = path.strip()
    if not path:
        return []
    kw = {"layer": layer} if layer else {}
    try:
        import fiona
        with fiona.open(path, **kw) as src:
            return list(src.schema["properties"].keys())
    except Exception:
        pass
    try:
        import pyogrio
        info = pyogrio.read_info(path, **kw)
        return list(info["fields"])
    except Exception:
        return []


def _labeled_row(parent, row: int, label: str, column_span: int = 1):
    """Return a (frame, entry) pair placed at *row* inside *parent*."""
    tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=3)
    entry = tk.Entry(parent, width=50)
    entry.grid(row=row, column=1, columnspan=column_span, sticky="ew", padx=6, pady=3)
    return entry


def _file_row(parent, row: int, label: str, save: bool = False, browse_title: str = "Select file",
              on_change=None, allow_dir: bool = False):
    """Return an Entry pre-equipped with a Browse button.

    *on_change*, if provided, is called with the selected path after browse.
    When *allow_dir* is True, FileGDB and Other… buttons are shown (FileGDB first).
    """
    tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=3)
    entry = tk.Entry(parent, width=44)
    entry.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=3)

    def _browse():
        _browse_file(entry, browse_title, save)
        if on_change:
            on_change(entry.get())

    def _browse_dir():
        path = filedialog.askdirectory(title=browse_title)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)
            if on_change:
                on_change(path)

    btn_frame = tk.Frame(parent)
    btn_frame.grid(row=row, column=2, padx=(2, 6), pady=3)
    if allow_dir:
        tk.Button(btn_frame, text="FileGDB…", command=_browse_dir).pack(side="left")
        tk.Button(btn_frame, text="Other…", command=_browse).pack(side="left", padx=(2, 0))
    else:
        tk.Button(btn_frame, text="Browse…", command=_browse).pack(side="left")
    return entry


def _folder_row(parent, row: int, label: str, browse_title: str = "Select folder"):
    """Return an Entry pre-equipped with a Browse button that opens a directory dialog."""
    tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=6, pady=3)
    entry = tk.Entry(parent, width=44)
    entry.grid(row=row, column=1, sticky="ew", padx=(6, 0), pady=3)

    def _browse():
        path = filedialog.askdirectory(title=browse_title)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)

    btn = tk.Button(parent, text="Browse…", command=_browse)
    btn.grid(row=row, column=2, padx=(2, 6), pady=3)
    return entry


def _check_row(parent, row: int, label: str):
    """Return a BooleanVar tied to a Checkbutton."""
    var = tk.BooleanVar()
    cb = tk.Checkbutton(parent, text=label, variable=var, anchor="w")
    cb.grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=2)
    return var


# ---------------------------------------------------------------------------
# Command builder helpers
# ---------------------------------------------------------------------------


def _add_opt(cmd: list, flag: str, value: str) -> None:
    """Append *flag value* to *cmd* when *value* is non-empty."""
    v = value.strip()
    if v:
        cmd += [flag, v]


def _add_multi(cmd: list, flag: str, value: str) -> None:
    """Repeat *flag val* for each comma/space-separated token in *value*."""
    for token in value.replace(",", " ").split():
        cmd += [flag, token]


# ---------------------------------------------------------------------------
# Field picker widget
# ---------------------------------------------------------------------------


class _FieldEntry(tk.Frame):
    """Entry with a 'Pick…' button for selecting comma-separated field names.

    Call :meth:`set_choices` to populate the picker list after fields are known.
    The widget's :meth:`get` returns the entry text, compatible with plain Entry.
    """

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._choices: list = []
        self.entry = tk.Entry(self, width=42)
        self.entry.pack(side="left", fill="x", expand=True)
        self._btn = tk.Button(self, text="Pick…", command=self._pick, padx=4)
        self._btn.pack(side="left", padx=(2, 0))

    def get(self) -> str:
        return self.entry.get()

    def set_choices(self, fields: list) -> None:
        self._choices = list(fields)

    def _pick(self):
        if not self._choices:
            return
        top = tk.Toplevel(self)
        top.title("Select fields")
        top.resizable(False, True)
        top.minsize(220, 160)

        current = {v.strip() for v in self.entry.get().replace(",", " ").split() if v.strip()}

        # Scrollable list of checkboxes
        container = tk.Frame(top)
        container.pack(fill="both", expand=True, padx=8, pady=8)
        vsb = ttk.Scrollbar(container, orient="vertical")
        canvas = tk.Canvas(container, yscrollcommand=vsb.set, highlightthickness=0)
        vsb.config(command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

        vars_ = []
        for field in self._choices:
            var = tk.BooleanVar(value=field in current)
            tk.Checkbutton(inner, text=field, variable=var, anchor="w").pack(fill="x")
            vars_.append((field, var))

        def _ok():
            selected = [f for f, v in vars_ if v.get()]
            self.entry.delete(0, tk.END)
            self.entry.insert(0, ", ".join(selected))
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))
        tk.Button(btn_frame, text="OK", command=_ok, padx=8).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Clear all", command=lambda: [v.set(False) for _, v in vars_]).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Cancel", command=top.destroy).pack(side="left", padx=4)

        top.grab_set()
        top.wait_window()


# ---------------------------------------------------------------------------
# Output console
# ---------------------------------------------------------------------------


class OutputConsole(tk.Frame):
    """Scrollable text widget that streams subprocess output."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self.text = scrolledtext.ScrolledText(
            self,
            state="disabled",
            wrap="word",
            font=("Courier", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
        )
        self.text.pack(fill="both", expand=True)

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.config(state="disabled")

    def append(self, text: str):
        self.text.config(state="normal")
        self.text.insert(tk.END, text)
        self.text.see(tk.END)
        self.text.config(state="disabled")

    def run_command(self, cmd: list, run_btn: tk.Button, copy_btn: tk.Button, logfile: str = None):
        """Execute *cmd* in a background thread, streaming output here and optionally to *logfile*."""
        self.clear()
        self.append("$ " + " ".join(cmd) + "\n\n")
        run_btn.config(state="disabled")

        def _worker():
            log_fh = None
            try:
                log_fh = open(logfile, "w") if logfile else None
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in proc.stdout:
                    self.after(0, self.append, line)
                    if log_fh:
                        log_fh.write(line)
                proc.wait()
                rc = proc.returncode
                exit_msg = f"\n[Process exited with code {rc}]\n"
                self.after(0, self.append, exit_msg)
                if log_fh:
                    log_fh.write(exit_msg)
            except FileNotFoundError:
                self.after(
                    0,
                    self.append,
                    "\n[ERROR] 'changedetector' not found on PATH.\n"
                    "Install it with:  pip install fit-changedetector\n",
                )
            finally:
                if log_fh:
                    log_fh.close()
                self.after(0, run_btn.config, {"state": "normal"})

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Compare tab
# ---------------------------------------------------------------------------


class CompareTab(tk.Frame):
    def __init__(self, parent, console: OutputConsole, **kw):
        super().__init__(parent, **kw)
        self.console = console
        self.columnconfigure(1, weight=1)
        self._build()

    def _build(self):
        r = 0
        # --- Input files ---
        self.file_a = _file_row(
            self, r, "Original file *", browse_title="Select original file",
            on_change=lambda p: self._populate_layers(p, self.layer_a), allow_dir=True,
        )
        self.file_a.bind("<FocusOut>", lambda e: self._populate_layers(self.file_a.get(), self.layer_a))
        self.file_a.bind("<Return>", lambda e: self._populate_layers(self.file_a.get(), self.layer_a))
        r += 1
        tk.Label(self, text="  └ Layer", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.layer_a = ttk.Combobox(self, width=47)
        self.layer_a.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        self.layer_a.bind("<<ComboboxSelected>>", lambda e: self._update_fields())
        r += 1
        self.file_b = _file_row(
            self, r, "New file *", browse_title="Select new file",
            on_change=lambda p: self._populate_layers(p, self.layer_b), allow_dir=True,
        )
        self.file_b.bind("<FocusOut>", lambda e: self._populate_layers(self.file_b.get(), self.layer_b))
        self.file_b.bind("<Return>", lambda e: self._populate_layers(self.file_b.get(), self.layer_b))
        r += 1
        tk.Label(self, text="  └ Layer", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.layer_b = ttk.Combobox(self, width=47)
        self.layer_b.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        self.layer_b.bind("<<ComboboxSelected>>", lambda e: self._update_fields())
        r += 1
        self.out_file = _folder_row(self, r, "Output folder", browse_title="Select output folder")
        r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        # --- Key / field options ---
        tk.Label(self, text="Primary key field(s)", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.primary_key = _FieldEntry(self)
        self.primary_key.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1
        tk.Label(self, text="Fields to INCLUDE in comparison", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.fields = _FieldEntry(self)
        self.fields.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1
        tk.Label(self, text="Fields to EXCLUDE from comparison", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.ignore_fields = _FieldEntry(self)
        self.ignore_fields.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1
        tk.Label(self, text="Hash field name", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.hash_key = ttk.Combobox(self, width=47)
        self.hash_key.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1
        tk.Label(self, text="Hash fields", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.hash_fields = _FieldEntry(self)
        self.hash_fields.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        # --- Misc options ---
        self.precision = _labeled_row(self, r, "Coordinate precision")
        self.precision.insert(0, "0.01")
        r += 1
        self.suffix_a = _labeled_row(self, r, "Column name suffix - original")
        self.suffix_a.insert(0, "original")
        r += 1
        self.suffix_b = _labeled_row(self, r, "Column name suffix - new")
        self.suffix_b.insert(0, "new")
        r += 1
        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        # --- Checkboxes ---
        self.drop_null = _check_row(self, r, "Drop null geometry")
        r += 1
        self.dump_inputs = _check_row(self, r, "Save input datasets to generated output .gdb")
        r += 1
        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        # --- Buttons ---
        btn_frame = tk.Frame(self)
        btn_frame.grid(row=r, column=0, columnspan=3, pady=6)
        self.run_btn = tk.Button(
            btn_frame,
            text="Run compare",
            command=self._run,
            padx=12,
            pady=4,
        )
        self.run_btn.pack(side="left", padx=4)
        self.copy_btn = tk.Button(btn_frame, text="Copy command", command=self._copy)
        self.copy_btn.pack(side="left", padx=4)

    def _populate_layers(self, path: str, combobox: ttk.Combobox) -> None:
        """Read layers from *path* and update *combobox* values."""
        layers = _list_layers(path)
        combobox["values"] = layers
        if layers:
            combobox.set(layers[0])
        else:
            combobox.set("")
        self._update_fields()

    def _update_fields(self) -> None:
        """Load fields from the selected sources/layers and update all field pickers."""
        fields_a = _list_fields(self.file_a.get(), self.layer_a.get() or None)
        fields_b = _list_fields(self.file_b.get(), self.layer_b.get() or None)
        if fields_a and fields_b:
            set_b = set(fields_b)
            available = [f for f in fields_a if f in set_b]
        else:
            available = fields_a or fields_b
        for widget in (self.primary_key, self.hash_fields, self.fields, self.ignore_fields):
            widget.set_choices(available)
        self.hash_key["values"] = available

    def _build_cmd(self) -> list:
        cmd = ["changedetector", "compare", "-v"]
        cmd.append(self.file_a.get().strip())
        cmd.append(self.file_b.get().strip())
        _add_opt(cmd, "--layer-a", self.layer_a.get())
        _add_opt(cmd, "--layer-b", self.layer_b.get())
        _add_multi(cmd, "-pk", self.primary_key.get())
        _add_opt(cmd, "-hk", self.hash_key.get())
        _add_multi(cmd, "-hf", self.hash_fields.get())
        _add_multi(cmd, "-f", self.fields.get())
        _add_multi(cmd, "-if", self.ignore_fields.get())
        folder = self.out_file.get().strip()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_path = os.path.join(folder, f"changedetector_{timestamp}.gdb") if folder else f"changedetector_{timestamp}.gdb"
        cmd += ["-o", out_path]
        _add_opt(cmd, "-p", self.precision.get())
        _add_opt(cmd, "-a", self.suffix_a.get())
        _add_opt(cmd, "-b", self.suffix_b.get())

        if self.drop_null.get():
            cmd.append("-d")
        if self.dump_inputs.get():
            cmd.append("-i")
        return cmd

    def _run(self):
        if not self.file_a.get().strip():
            self.console.append("[ERROR] Original file is required.\n")
            return
        cmd = self._build_cmd()
        out_path = cmd[cmd.index("-o") + 1]
        logfile = os.path.splitext(out_path)[0] + ".txt"
        self.console.run_command(cmd, self.run_btn, self.copy_btn, logfile=logfile)

    def _copy(self):
        cmd = self._build_cmd()
        self.clipboard_clear()
        self.clipboard_append(" ".join(cmd))


# ---------------------------------------------------------------------------
# Add Hash Key tab
# ---------------------------------------------------------------------------


class AddHashKeyTab(tk.Frame):
    def __init__(self, parent, console: OutputConsole, **kw):
        super().__init__(parent, **kw)
        self.console = console
        self.columnconfigure(1, weight=1)
        self._build()

    def _build(self):
        r = 0
        # --- Input file ---
        self.in_file = _file_row(
            self, r, "Input file *", browse_title="Select input file",
            on_change=lambda p: self._populate_layers(p, self.in_layer),
        )
        self.in_file.bind("<FocusOut>", lambda e: self._populate_layers(self.in_file.get(), self.in_layer))
        self.in_file.bind("<Return>", lambda e: self._populate_layers(self.in_file.get(), self.in_layer))
        r += 1
        tk.Label(self, text="  └ Layer", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.in_layer = ttk.Combobox(self, width=47)
        self.in_layer.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        self.in_layer.bind("<<ComboboxSelected>>", lambda e: self._update_fields())
        r += 1
        self.out_file = _file_row(
            self, r, "Output file *", save=True, browse_title="Save output as"
        )
        r += 1
        self.out_layer = _labeled_row(self, r, "Output layer")
        r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        # --- Hash options ---
        self.hash_key = _labeled_row(self, r, "Output hash field name")
        r += 1
        tk.Label(self, text="Hash fields", anchor="w").grid(row=r, column=0, sticky="w", padx=6, pady=3)
        self.hash_fields = _FieldEntry(self)
        self.hash_fields.grid(row=r, column=1, columnspan=2, sticky="ew", padx=6, pady=3)
        r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        self.drop_null = _check_row(self, r, "Drop null geometry")
        r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=6
        )
        r += 1

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=r, column=0, columnspan=3, pady=6)
        self.run_btn = tk.Button(
            btn_frame,
            text="Run add-hash-key",
            command=self._run,
            padx=12,
            pady=4,
        )
        self.run_btn.pack(side="left", padx=4)
        self.copy_btn = tk.Button(btn_frame, text="Copy command", command=self._copy)
        self.copy_btn.pack(side="left", padx=4)

    def _populate_layers(self, path: str, combobox: ttk.Combobox) -> None:
        layers = _list_layers(path)
        combobox["values"] = layers
        if layers:
            combobox.set(layers[0])
        else:
            combobox.set("")
        self._update_fields()

    def _update_fields(self) -> None:
        fields = _list_fields(self.in_file.get(), self.in_layer.get() or None)
        self.hash_fields.set_choices(fields)

    def _build_cmd(self) -> list:
        cmd = ["changedetector", "add-hash-key", "-v"]
        cmd.append(self.in_file.get().strip())
        cmd.append(self.out_file.get().strip())
        _add_opt(cmd, "--in-layer", self.in_layer.get())
        _add_opt(cmd, "--out-layer", self.out_layer.get())
        _add_opt(cmd, "-hk", self.hash_key.get())
        _add_multi(cmd, "-hf", self.hash_fields.get())

        if self.drop_null.get():
            cmd.append("-d")
        return cmd

    def _run(self):
        cmd = self._build_cmd()
        self.console.run_command(cmd, self.run_btn, self.copy_btn)

    def _copy(self):
        cmd = self._build_cmd()
        self.clipboard_clear()
        self.clipboard_append(" ".join(cmd))


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FIT ChangeDetector GUI")
        self._build()

    def _build(self):
        # Top pane: notebook tabs
        paned = tk.PanedWindow(self, orient="vertical", sashrelief="raised", sashwidth=6)
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Notebook (top two-thirds) ---
        nb_frame = tk.Frame(paned)
        paned.add(nb_frame, minsize=100)

        nb = ttk.Notebook(nb_frame)
        nb.pack(fill="both", expand=True)

        # Shared output console (bottom, default minimum size)
        console_frame = tk.LabelFrame(paned, text="Output")
        paned.add(console_frame, minsize=120)
        self.console = OutputConsole(console_frame)
        self.console.pack(fill="both", expand=True, padx=4, pady=4)

        # --- Tabs ---
        compare_scroll = _scrollable(nb)
        compare_tab = CompareTab(compare_scroll.inner, self.console)
        compare_tab.pack(fill="both", expand=True)
        nb.add(compare_scroll, text="  Compare  ")

        hash_scroll = _scrollable(nb)
        hash_tab = AddHashKeyTab(hash_scroll.inner, self.console)
        hash_tab.pack(fill="both", expand=True)
        nb.add(hash_scroll, text="  Add Hash Key  ")

        # Status bar
        self.status = tk.Label(self, text="Ready", anchor="w", relief="sunken", bd=1)
        self.status.pack(side="bottom", fill="x")

        def _fit():
            self.update_idletasks()
            # Size window to fit all compare tab parameters + 120px console
            form_h = compare_tab.winfo_reqheight()
            nb_h = nb.winfo_reqheight()
            status_h = self.status.winfo_reqheight()
            win_h = form_h + (nb_h - compare_scroll.winfo_reqheight()) + 120 + status_h + 16
            win_w = compare_tab.winfo_reqwidth() + 16
            self.geometry(f"{win_w}x{win_h}")
            self.minsize(win_w, win_h)
            self.update_idletasks()
            paned.sash_place(0, 0, paned.winfo_height() - 120)

        self.after(50, _fit)


# ---------------------------------------------------------------------------
# Scrollable container helper
# ---------------------------------------------------------------------------


class _scrollable(tk.Frame):
    """A Frame with a vertical scrollbar, exposing an .inner frame."""

    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        vsb = ttk.Scrollbar(self, orient="vertical")
        vsb.pack(side="right", fill="y")
        canvas = tk.Canvas(self, yscrollcommand=vsb.set, highlightthickness=0)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=canvas.yview)

        self.inner = tk.Frame(canvas)
        self.inner.columnconfigure(1, weight=1)
        window_id = canvas.create_window((0, 0), window=self.inner, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_resize(event):
            canvas.itemconfig(window_id, width=event.width)

        self.inner.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_canvas_resize)

        # Mouse-wheel scrolling
        def _on_wheel(event):
            if sys.platform == "darwin":
                canvas.yview_scroll(-int(event.delta), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(-int(event.delta / 120), "units")

        canvas.bind_all("<MouseWheel>", _on_wheel)
        canvas.bind_all("<Button-4>", _on_wheel)
        canvas.bind_all("<Button-5>", _on_wheel)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
