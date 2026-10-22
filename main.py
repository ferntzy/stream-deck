"""RX75 Stream Pad: turn selected keyboard keys into Windows actions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, filedialog, messagebox, simpledialog, ttk
import tkinter as tk

try:
    import keyboard
except ImportError:
    keyboard = None


APP_NAME = "RX75 Stream Pad"
CONFIG_PATH = Path(__file__).with_name("mappings.json")
DEFAULT_PROFILES = ("Work", "Streaming", "Gaming")
QUICK_TOGGLE_HOTKEY = "ctrl+alt+f12"
MEDIA_VK = {
    "play/pause": 0xB3,
    "next track": 0xB0,
    "previous track": 0xB1,
    "volume mute": 0xAD,
    "volume up": 0xAF,
    "volume down": 0xAE,
}
ACTION_NAMES = {
    "Open app/file": "open",
    "Open website": "website",
    "Send shortcut": "shortcut",
    "Type saved text": "text",
    "Show saved text popup": "note",
    "Media control": "media",
    "Play sound clip": "sound",
    "Stop all sounds": "stop_sound",
    "Show image popup": "image",
    "Send another key": "send_key",
}


def load_profiles() -> tuple[dict[str, list[dict[str, str]]], str]:
    if not CONFIG_PATH.exists():
        return {name: [] for name in DEFAULT_PROFILES}, "Work"
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # Keep mappings created by earlier versions and place them in Work.
        if isinstance(data, list):
            profiles = {name: [] for name in DEFAULT_PROFILES}
            profiles["Work"] = [row for row in data if isinstance(row, dict) and row.get("trigger")]
            return profiles, "Work"
        if not isinstance(data, dict) or not isinstance(data.get("profiles"), dict):
            raise ValueError("Expected a profile configuration")
        profiles = {name: [] for name in DEFAULT_PROFILES}
        for name, rows in data["profiles"].items():
            if isinstance(name, str) and isinstance(rows, list):
                profiles[name] = [row for row in rows if isinstance(row, dict) and row.get("trigger")]
        active = data.get("active_profile", "Work")
        if active not in profiles:
            active = "Work"
        return profiles, active
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Could not read {CONFIG_PATH.name}: {exc}") from exc


def save_profiles(profiles: dict[str, list[dict[str, str]]], active_profile: str) -> None:
    payload = {"version": 1, "active_profile": active_profile, "profiles": profiles}
    CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class MappingDialog(tk.Toplevel):
    def __init__(self, parent: "StreamPadApp", row: dict[str, str] | None = None):
        super().__init__(parent)
        self.app = parent
        self.result: dict[str, str] | None = None
        self.title("Edit key action" if row else "Add key action")
        self.configure(bg="#111827")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        values = row or {"trigger": "", "label": "", "action": "open", "value": "", "duration": "forever"}
        pad = ttk.Frame(self, padding=18)
        pad.pack(fill=BOTH, expand=True)

        ttk.Label(pad, text="Key to intercept").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.trigger_var = tk.StringVar(value=values.get("trigger", ""))
        trigger_line = ttk.Frame(pad)
        trigger_line.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.trigger_entry = ttk.Entry(trigger_line, textvariable=self.trigger_var, width=27)
        self.trigger_entry.pack(side=LEFT, fill=X, expand=True)
        self.capture_btn = ttk.Button(trigger_line, text="Capture key", command=self.capture_key)
        self.capture_btn.pack(side=RIGHT, padx=(8, 0))

        ttk.Label(pad, text="Button label").grid(row=2, column=0, sticky="w", pady=(0, 6))
        self.label_var = tk.StringVar(value=values.get("label", ""))
        ttk.Entry(pad, textvariable=self.label_var, width=44).grid(row=3, column=0, sticky="ew", pady=(0, 12))

        ttk.Label(pad, text="Action").grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.action_display_var = tk.StringVar(value=next((k for k, v in ACTION_NAMES.items() if v == values.get("action")), "Open app/file"))
        action_box = ttk.Combobox(pad, textvariable=self.action_display_var, values=list(ACTION_NAMES), state="readonly", width=41)
        action_box.grid(row=5, column=0, sticky="ew", pady=(0, 12))
        action_box.bind("<<ComboboxSelected>>", self._action_changed)

        ttk.Label(pad, text="Action value").grid(row=6, column=0, sticky="w", pady=(0, 6))
        value_line = ttk.Frame(pad)
        value_line.grid(row=7, column=0, sticky="ew", pady=(0, 10))
        self.value_entry = ttk.Entry(value_line, width=36)
        self.value_entry.insert(0, values.get("value", ""))
        self.value_entry.pack(side=LEFT, fill=X, expand=True)
        self.value_text = tk.Text(value_line, width=36, height=5, wrap="word", font=("Segoe UI", 10), bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", padx=7, pady=6)
        self.value_text.insert("1.0", values.get("value", ""))
        self.browse_btn = ttk.Button(value_line, text="Browse…", command=self.browse_file)
        self.browse_btn.pack(side=RIGHT, padx=(8, 0))

        ttk.Label(pad, text="Popup duration").grid(row=8, column=0, sticky="w", pady=(0, 6))
        self.duration_var = tk.StringVar(value=values.get("duration", "forever"))
        self.duration_box = ttk.Combobox(pad, textvariable=self.duration_var, values=("Until closed", "1 second", "3 seconds", "5 seconds", "10 seconds", "30 seconds", "60 seconds"), state="readonly", width=41)
        duration_labels = {"forever": "Until closed", "1": "1 second", "3": "3 seconds", "5": "5 seconds", "10": "10 seconds", "30": "30 seconds", "60": "60 seconds"}
        self.duration_var.set(duration_labels.get(self.duration_var.get(), "Until closed"))
        self.duration_box.grid(row=9, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(pad, text="Sound: choose WAV/MP3/OGG. Image: choose an image file. Saved text popups can contain multiple lines. Popup duration applies to image and text popups.", wraplength=420).grid(row=10, column=0, sticky="w", pady=(0, 12))
        buttons = ttk.Frame(pad)
        buttons.grid(row=11, column=0, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Save action", command=self.accept).pack(side=LEFT)
        pad.columnconfigure(0, weight=1)
        self.bind("<Return>", lambda _event: self.accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self._action_changed()
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def capture_key(self) -> None:
        if keyboard is None:
            messagebox.showerror("Keyboard support missing", "Install the app requirements first: pip install -r requirements.txt", parent=self)
            return
        self.capture_btn.configure(text="Press a key…", state="disabled")
        self.trigger_var.set("")

        def wait_for_key() -> None:
            try:
                key = keyboard.read_key(suppress=True)
                self.after(0, lambda: self._finish_capture(key))
            except Exception as exc:  # surfaced in the UI
                self.after(0, lambda: self._capture_failed(str(exc)))

        threading.Thread(target=wait_for_key, daemon=True).start()

    def _finish_capture(self, key: str) -> None:
        self.trigger_var.set(key.lower())
        self.capture_btn.configure(text="Capture key", state="normal")
        (self.value_text if self.value_text.winfo_manager() else self.value_entry).focus_set()

    def _capture_failed(self, error: str) -> None:
        self.capture_btn.configure(text="Capture key", state="normal")
        messagebox.showerror("Could not capture key", error, parent=self)

    def browse_file(self) -> None:
        if ACTION_NAMES[self.action_display_var.get()] == "sound":
            filetypes = [("Audio files", "*.wav *.mp3 *.ogg"), ("All files", "*.*")]
            title = "Choose a sound clip"
        elif ACTION_NAMES[self.action_display_var.get()] == "image":
            filetypes = [("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("All files", "*.*")]
            title = "Choose an image to show"
        else:
            filetypes = [("All files", "*.*")]
            title = "Choose an app or file"
        path = filedialog.askopenfilename(parent=self, title=title, filetypes=filetypes)
        if path:
            self.value_entry.delete(0, END)
            self.value_entry.insert(0, path)

    def _action_changed(self, _event=None) -> None:
        action = ACTION_NAMES[self.action_display_var.get()]
        wants_text = action == "note"
        current_is_text = bool(self.value_text.winfo_manager())
        if wants_text != current_is_text:
            current = self._read_value()
            if current_is_text:
                self.value_text.pack_forget()
                self.value_entry.pack(side=LEFT, fill=X, expand=True, before=self.browse_btn)
                self.value_entry.delete(0, END)
                self.value_entry.insert(0, current)
            else:
                self.value_entry.pack_forget()
                self.value_text.pack(side=LEFT, fill=X, expand=True, before=self.browse_btn)
                self.value_text.delete("1.0", END)
                self.value_text.insert("1.0", current)
        is_stop = action == "stop_sound"
        file_action = action in ("open", "sound", "image")
        self.value_entry.configure(state="disabled" if is_stop else "normal")
        self.value_text.configure(state="disabled" if is_stop else "normal")
        self.browse_btn.configure(state="normal" if file_action else "disabled")
        self.duration_box.configure(state="readonly" if action in ("image", "note") else "disabled")
        self.capture_btn.configure(state="normal")

    def _read_value(self) -> str:
        if self.value_text.winfo_manager():
            return self.value_text.get("1.0", "end-1c").strip()
        return self.value_entry.get().strip()

    def accept(self) -> None:
        trigger = self.trigger_var.get().strip().lower()
        label = self.label_var.get().strip() or trigger.upper()
        display = self.action_display_var.get()
        value = self._read_value()
        if not trigger:
            messagebox.showwarning("Key required", "Capture or enter a key to intercept.", parent=self)
            return
        action = ACTION_NAMES[display]
        if not value and action != "stop_sound":
            messagebox.showwarning("Action required", "Enter the action value.", parent=self)
            return
        duration_labels = {"Until closed": "forever", "1 second": "1", "3 seconds": "3", "5 seconds": "5", "10 seconds": "10", "30 seconds": "30", "60 seconds": "60"}
        result = {"trigger": trigger, "label": label, "action": action, "value": value}
        if action in ("image", "note"):
            result["duration"] = duration_labels.get(self.duration_var.get(), "forever")
        self.result = result
        self.destroy()


class StreamPadApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("940x620")
        self.minsize(760, 500)
        self.configure(bg="#0b1220")
        self.profiles: dict[str, list[dict[str, str]]] = {name: [] for name in DEFAULT_PROFILES}
        self.current_profile = "Work"
        self.mappings: list[dict[str, str]] = self.profiles[self.current_profile]
        self.hotkey_handles: list[tuple[str, object]] = []
        self.quick_toggle_handle: object | None = None
        self.blocked_key_pressed: set[str] = set()
        self.sound_cache: dict[str, object] = {}
        self.active = False
        self._executing = False
        self.volume_var = tk.DoubleVar(value=80)
        self.status_var = tk.StringVar(value="Stopped — your RX75 works as a normal keyboard.")
        self.active_var = tk.BooleanVar(value=False)
        self._style()
        self._build()
        try:
            self.profiles, self.current_profile = load_profiles()
            self.mappings = self.profiles[self.current_profile]
            self.profile_box.configure(values=list(self.profiles))
            self.profile_var.set(self.current_profile)
        except RuntimeError as exc:
            messagebox.showerror("Profile file problem", str(exc), parent=self)
        self._install_quick_toggle()
        self._refresh_rows()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#0b1220", foreground="#e5e7eb", fieldbackground="#111827", font=("Segoe UI", 10))
        style.configure("TFrame", background="#0b1220")
        style.configure("TLabel", background="#0b1220", foreground="#e5e7eb")
        style.configure("Header.TLabel", font=("Segoe UI", 20, "bold"), foreground="#f9fafb")
        style.configure("Sub.TLabel", foreground="#9ca3af")
        style.configure("TButton", background="#1f2937", foreground="#f9fafb", padding=(10, 7), borderwidth=0)
        style.map("TButton", background=[("active", "#374151"), ("disabled", "#1f2937")])
        style.configure("Accent.TButton", background="#f97316", foreground="#111827", font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#fb923c")])
        style.configure("Treeview", background="#111827", fieldbackground="#111827", foreground="#e5e7eb", rowheight=34, borderwidth=0)
        style.configure("Treeview.Heading", background="#1f2937", foreground="#cbd5e1", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#7c2d12")])
        style.configure("TCheckbutton", background="#0b1220", foreground="#e5e7eb")

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=22)
        outer.pack(fill=BOTH, expand=True)
        top = ttk.Frame(outer)
        top.pack(fill=X)
        ttk.Label(top, text="RX75 Stream Pad", style="Header.TLabel").pack(side=LEFT)
        ttk.Button(top, text="Add key action", style="Accent.TButton", command=self.add_mapping).pack(side=RIGHT)
        ttk.Label(outer, text="Turn selected RX75 keys into app launches, shortcuts, text snippets, websites, and media controls.", style="Sub.TLabel").pack(anchor="w", pady=(5, 18))

        cards = ttk.Frame(outer)
        cards.pack(fill=X, pady=(0, 16))
        self.toggle = ttk.Checkbutton(cards, text="Enable mapped keys", variable=self.active_var, command=self.toggle_active)
        self.toggle.pack(side=LEFT)
        ttk.Label(cards, text="Profile").pack(side=LEFT, padx=(20, 7))
        self.profile_var = tk.StringVar(value=self.current_profile)
        self.profile_box = ttk.Combobox(cards, textvariable=self.profile_var, values=list(self.profiles), state="readonly", width=13)
        self.profile_box.pack(side=LEFT)
        self.profile_box.bind("<<ComboboxSelected>>", self.change_profile)
        ttk.Button(cards, text="New profile", command=self.add_profile).pack(side=LEFT, padx=(7, 0))
        ttk.Button(cards, text="Delete profile", command=self.delete_profile).pack(side=LEFT, padx=(7, 0))
        ttk.Label(cards, text="Sound volume").pack(side=LEFT, padx=(24, 8))
        ttk.Scale(cards, from_=0, to=100, variable=self.volume_var, command=self.set_sound_volume, length=150).pack(side=LEFT)
        self.volume_label = ttk.Label(cards, text="80%", style="Sub.TLabel")
        self.volume_label.pack(side=LEFT, padx=(8, 0))
        ttk.Button(cards, text="Edit selected", command=self.edit_selected).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(cards, text="Remove", command=self.remove_selected).pack(side=RIGHT)

        table_wrap = ttk.Frame(outer)
        table_wrap.pack(fill=BOTH, expand=True)
        cols = ("trigger", "label", "action", "value")
        self.table = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="browse")
        for col, title, width in (("trigger", "KEY", 120), ("label", "PAD LABEL", 140), ("action", "ACTION", 160), ("value", "VALUE", 420)):
            self.table.heading(col, text=title)
            self.table.column(col, width=width, anchor="w")
        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=yscroll.set)
        self.table.pack(side=LEFT, fill=BOTH, expand=True)
        yscroll.pack(side=RIGHT, fill=Y)
        self.table.bind("<Double-1>", lambda _event: self.edit_selected())

        footer = ttk.Frame(outer)
        footer.pack(fill=X, pady=(14, 0))
        ttk.Label(footer, textvariable=self.status_var, style="Sub.TLabel").pack(side=LEFT)
        ttk.Button(footer, text="Save mappings", command=self.save).pack(side=RIGHT)
        ttk.Label(outer, text=f"Mapped keys lose their normal action while enabled. Unmapped keys type normally. Toggle mappings anytime with {QUICK_TOGGLE_HOTKEY.upper()}.", style="Sub.TLabel", wraplength=870).pack(anchor="w", pady=(10, 0))
        ttk.Label(outer, text="Use wired mode for setup; RGB remains controlled in Zifriend’s app.", style="Sub.TLabel").pack(anchor="w", pady=(5, 0))

    def _refresh_rows(self) -> None:
        for item in self.table.get_children():
            self.table.delete(item)
        for index, row in enumerate(self.mappings):
            action = next((name for name, value in ACTION_NAMES.items() if value == row.get("action")), row.get("action", ""))
            if row.get("action") in ("image", "note"):
                seconds = row.get("duration", "forever")
                duration_text = "Until closed" if seconds == "forever" else f"{seconds}s"
                action = f"{action} · {duration_text}"
            self.table.insert("", END, iid=str(index), values=(row.get("trigger", ""), row.get("label", ""), action, row.get("value", "")))

    def change_profile(self, _event=None) -> None:
        selected = self.profile_var.get()
        if selected == self.current_profile or selected not in self.profiles:
            return
        self._unregister_hotkeys()
        self.current_profile = selected
        self.mappings = self.profiles[selected]
        self._refresh_rows()
        self.save(silent=True)
        if self.active_var.get():
            self._register_hotkeys()
        self.status_var.set(f"Profile: {selected}")

    def add_profile(self) -> None:
        name = simpledialog.askstring("New profile", "Profile name:", parent=self)
        if not name:
            return
        name = name.strip()
        if not name or name in self.profiles:
            messagebox.showwarning("Profile name", "Choose a non-empty name that is not already used.", parent=self)
            return
        self.profiles[name] = []
        self.profile_box.configure(values=list(self.profiles))
        self.profile_var.set(name)
        self.change_profile()

    def delete_profile(self) -> None:
        if self.current_profile in DEFAULT_PROFILES:
            messagebox.showinfo("Starter profile", "Work, Streaming, and Gaming are built-in profiles and cannot be deleted.", parent=self)
            return
        if not messagebox.askyesno("Delete profile", f"Delete the {self.current_profile!r} profile and its mappings?", parent=self):
            return
        self._unregister_hotkeys()
        del self.profiles[self.current_profile]
        self.current_profile = "Work"
        self.mappings = self.profiles[self.current_profile]
        self.profile_var.set(self.current_profile)
        self.profile_box.configure(values=list(self.profiles))
        self._refresh_rows()
        self.save(silent=True)
        if self.active_var.get():
            self._register_hotkeys()

    def add_mapping(self) -> None:
        dialog = MappingDialog(self)
        self.wait_window(dialog)
        if dialog.result:
            if any(row.get("trigger") == dialog.result["trigger"] for row in self.mappings):
                messagebox.showwarning("Key already assigned", "That key already has an action. Edit or remove its existing mapping first.", parent=self)
                return
            self.mappings.append(dialog.result)
            self._refresh_rows()
            self.save(silent=True)
            if self.active:
                self._register_hotkeys()

    def edit_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("Select a mapping", "Choose a key action first.", parent=self)
            return
        index = int(selected[0])
        dialog = MappingDialog(self, self.mappings[index])
        self.wait_window(dialog)
        if dialog.result:
            if any(i != index and row.get("trigger") == dialog.result["trigger"] for i, row in enumerate(self.mappings)):
                messagebox.showwarning("Key already assigned", "That key already has an action. Choose another key or remove the duplicate mapping.", parent=self)
                return
            self.mappings[index] = dialog.result
            self._refresh_rows()
            self.save(silent=True)
            if self.active:
                self._register_hotkeys()

    def remove_selected(self) -> None:
        selected = self.table.selection()
        if not selected:
            return
        del self.mappings[int(selected[0])]
        self._refresh_rows()
        self.save(silent=True)
        if self.active:
            self._register_hotkeys()

    def save(self, silent: bool = False) -> None:
        try:
            self.profiles[self.current_profile] = self.mappings
            save_profiles(self.profiles, self.current_profile)
            if not silent:
                self.status_var.set(f"Saved {len(self.mappings)} action(s) in {self.current_profile}.")
        except OSError as exc:
            messagebox.showerror("Could not save", str(exc), parent=self)

    def toggle_active(self) -> None:
        if self.active_var.get():
            self._register_hotkeys()
        else:
            self._unregister_hotkeys()

    def _install_quick_toggle(self) -> None:
        if keyboard is None:
            return
        try:
            self.quick_toggle_handle = keyboard.add_hotkey(
                QUICK_TOGGLE_HOTKEY,
                lambda: self.after(0, self._toggle_from_hotkey),
                suppress=True,
            )
        except Exception as exc:
            self.status_var.set(f"Quick toggle unavailable: {exc}")

    def _toggle_from_hotkey(self) -> None:
        self.active_var.set(not self.active_var.get())
        self.toggle_active()
        state = "enabled" if self.active_var.get() else "disabled"
        self.status_var.set(f"Mappings {state} with {QUICK_TOGGLE_HOTKEY.upper()}.")

    def _register_hotkeys(self) -> None:
        self._unregister_hotkeys()
        if keyboard is None:
            self.active_var.set(False)
            messagebox.showerror("Keyboard support missing", "Run install.bat first, then restart this app.", parent=self)
            return
        errors = []
        for row in self.mappings:
            trigger = row["trigger"].strip().lower()
            try:
                if "+" not in trigger and "," not in trigger:
                    # A blocking key hook suppresses every down/up event for this
                    # physical key before it reaches browsers or other apps.
                    def on_mapped_key(event, current=row, key=trigger):
                        if event.event_type == keyboard.KEY_DOWN and key not in self.blocked_key_pressed:
                            self.blocked_key_pressed.add(key)
                            self.after(0, lambda: self.run_action(current))
                        elif event.event_type == keyboard.KEY_UP:
                            self.blocked_key_pressed.discard(key)
                        return False

                    handle = keyboard.hook_key(trigger, on_mapped_key, suppress=True)
                    self.hotkey_handles.append(("hook", handle))
                else:
                    handle = keyboard.add_hotkey(trigger, lambda current=row: self.after(0, lambda: self.run_action(current)), suppress=True)
                    self.hotkey_handles.append(("hotkey", handle))
            except Exception as exc:
                errors.append(f"{trigger}: {exc}")
        self.active = bool(self.hotkey_handles)
        if errors:
            messagebox.showwarning("Some keys could not be mapped", "\n".join(errors), parent=self)
        if self.active:
            self.active_var.set(True)
            self.status_var.set(f"Active — intercepting {len(self.hotkey_handles)} mapped key(s).")
        else:
            self.active_var.set(False)
            self.status_var.set("No valid mappings enabled.")

    def _unregister_hotkeys(self) -> None:
        if keyboard is not None:
            for kind, handle in self.hotkey_handles:
                try:
                    if kind == "hook":
                        keyboard.unhook(handle)
                    else:
                        keyboard.remove_hotkey(handle)
                except Exception:
                    pass
        self.hotkey_handles.clear()
        self.blocked_key_pressed.clear()
        self.active = False
        if hasattr(self, "status_var") and not self.active_var.get():
            self.status_var.set("Stopped — your RX75 works as a normal keyboard.")

    def run_action(self, row: dict[str, str]) -> None:
        if self._executing:
            return
        self._executing = True
        try:
            action, value = row.get("action"), row.get("value", "")
            if action == "open":
                if sys.platform == "win32":
                    os.startfile(value)  # type: ignore[attr-defined]
                else:
                    subprocess.Popen([value])
            elif action == "website":
                webbrowser.open(value)
            elif action == "shortcut":
                if keyboard is None:
                    raise RuntimeError("Keyboard support is not installed")
                keyboard.send(value)
            elif action == "text":
                if keyboard is None:
                    raise RuntimeError("Keyboard support is not installed")
                keyboard.write(value, delay=0.01)
            elif action == "media":
                self._send_media(value)
            elif action == "sound":
                self._play_sound(value)
            elif action == "stop_sound":
                self._stop_sounds()
            elif action == "image":
                self._show_image(value, row.get("duration", "forever"))
            elif action == "note":
                self._show_note(row.get("label") or row.get("trigger", "Saved text"), value, row.get("duration", "forever"))
            elif action == "send_key":
                if keyboard is None:
                    raise RuntimeError("Keyboard support is not installed")
                keyboard.send(value)
            else:
                raise ValueError(f"Unsupported action: {action}")
            self.status_var.set(f"Ran: {row.get('label') or row.get('trigger')}")
        except Exception as exc:
            self.status_var.set(f"Action failed: {exc}")
            self.after(0, lambda error=str(exc): messagebox.showerror("Action failed", error, parent=self))
        finally:
            self.after(250, self._clear_execution_guard)

    def _clear_execution_guard(self) -> None:
        self._executing = False

    def set_sound_volume(self, _value=None) -> None:
        volume = max(0.0, min(1.0, self.volume_var.get() / 100))
        if hasattr(self, "volume_label"):
            self.volume_label.configure(text=f"{round(volume * 100)}%")
        for sound in self.sound_cache.values():
            try:
                sound.set_volume(volume)
            except Exception:
                pass

    def _play_sound(self, path: str) -> None:
        if not Path(path).is_file():
            raise FileNotFoundError(f"Sound file not found: {path}")
        try:
            import pygame
        except ImportError as exc:
            raise RuntimeError("Soundboard support is missing. Run install.bat again to install pygame.") from exc
        if not pygame.mixer.get_init():
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
        sound = self.sound_cache.get(path)
        if sound is None:
            sound = pygame.mixer.Sound(path)
            self.sound_cache[path] = sound
        sound.set_volume(max(0.0, min(1.0, self.volume_var.get() / 100)))
        channel = sound.play()
        if channel is None:
            raise RuntimeError("All sound channels are busy. Stop a sound or wait for playback to finish.")

    @staticmethod
    def _popup_timeout(popup: tk.Toplevel, duration: str) -> None:
        if duration == "forever":
            return
        try:
            seconds = max(1, min(3600, int(duration)))
        except (TypeError, ValueError):
            return
        popup.after(seconds * 1000, lambda: popup.winfo_exists() and popup.destroy())

    def _show_image(self, path: str, duration: str = "forever") -> None:
        if not Path(path).is_file():
            raise FileNotFoundError(f"Image file not found: {path}")
        try:
            from PIL import Image, ImageTk
        except ImportError as exc:
            raise RuntimeError("Image popup support is missing. Run install.bat again to install Pillow.") from exc
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail((1100, 760))
        popup = tk.Toplevel(self)
        popup.title(Path(path).name)
        popup.configure(bg="#0b1220")
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(popup, image=photo, bg="#0b1220", borderwidth=0)
        label.image = photo
        label.pack(padx=10, pady=10)
        popup.bind("<Escape>", lambda _event: popup.destroy())
        self._popup_timeout(popup, duration)
        popup.focus_force()

    def _show_note(self, title: str, text: str, duration: str = "forever") -> None:
        popup = tk.Toplevel(self)
        popup.title(f"Saved text — {title}")
        popup.configure(bg="#0b1220")
        popup.geometry("520x320")
        popup.minsize(320, 180)
        frame = ttk.Frame(popup, padding=12)
        frame.pack(fill=BOTH, expand=True)
        note = tk.Text(frame, wrap="word", font=("Segoe UI", 11), bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", padx=10, pady=10)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=note.yview)
        note.configure(yscrollcommand=scrollbar.set)
        note.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)
        note.insert("1.0", text)
        note.configure(state="disabled")
        popup.bind("<Escape>", lambda _event: popup.destroy())
        self._popup_timeout(popup, duration)
        popup.focus_force()

    @staticmethod
    def _stop_sounds() -> None:
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.stop()
        except ImportError:
            pass

    @staticmethod
    def _send_media(action: str) -> None:
        action = action.strip().lower()
        if action not in MEDIA_VK:
            raise ValueError("Choose one of: " + ", ".join(MEDIA_VK))
        if sys.platform == "win32":
            import ctypes
            vk = MEDIA_VK[action]
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        elif keyboard is not None:
            keyboard.send(action)
        else:
            raise RuntimeError("Media controls require Windows or the keyboard package")

    def close(self) -> None:
        self._unregister_hotkeys()
        if keyboard is not None and self.quick_toggle_handle is not None:
            try:
                keyboard.remove_hotkey(self.quick_toggle_handle)
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    app = StreamPadApp()
    app.mainloop()
