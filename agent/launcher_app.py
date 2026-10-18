"""Windows launcher entry point; dashboard/agent workers keep pipe-based Stop."""

import argparse
import asyncio
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_runtime import data_root
from factorio_theme import apply_theme


def dashboard_component():
    from autoengineer_dashboard import Dashboard

    root = tk.Tk()
    view = Dashboard(root)
    commands = queue.Queue()
    ever_active = False
    status_path = os.environ.get("AUTOENGINEER_LAUNCHER_STATUS")

    def state(closed=False):
        nonlocal ever_active
        ever_active = (
            ever_active or view.proc is not None or view.stop_requested or view.stop_confirmed
        )
        if status_path:
            data = dict(
                live=bool(
                    view.live_view.available
                    and view.live_view.received
                    and time.monotonic() - view.live_view.received < 5
                ),
                mode=view.current_mode,
                agent_active=view.proc is not None,
                ever_active=ever_active,
                stop_confirmed=view.stop_confirmed,
                closed=closed,
            )
            path = Path(status_path)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(data))
            temp.replace(path)

    original = view.close_display

    def close():
        state(True)
        original()

    view.close_display = close

    def reader():
        if sys.stdin is None:
            return
        for line in sys.stdin:
            if line.strip().lower() in ("q", "stop"):
                commands.put("stop")
                return
        commands.put("stop")

    threading.Thread(target=reader, daemon=True).start()

    def poll():
        if not commands.empty():
            commands.get()
            view.closing = True
            view.start_button.configure(state="disabled")
            if view.proc is not None:
                view.stop()
            else:
                view.close_display()
                return
        state()
        root.after(500, poll)

    root.after(500, poll)
    root.mainloop()


class Launcher:
    def __init__(self, root, profile=None):
        from launcher_services import Profile, Supervisor

        self.root = root
        self.supervisor = None
        self.events = queue.Queue()
        self.closing = False
        self.health_busy = False
        self.last_health = 0
        self.Profile = Profile
        self.Supervisor = Supervisor
        apply_theme(root)
        root.title("AutoEngineer | Launch and connect")
        root.geometry("900x570")
        root.minsize(850, 540)
        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AUTOENGINEER  /  LAUNCH CONTROL", style="Heading.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            frame, text="TEST WORLD  /  LOCAL MODEL  /  SUPERVISED DASHBOARD", style="Muted.TLabel"
        ).pack(anchor="w", pady=(3, 15))
        self.profile = tk.StringVar(value=str(profile or data_root() / "launcher.local.json"))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.profile).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Choose setup", command=self.choose).pack(side="left", padx=(8, 0))
        self.labels = {}
        for key, title in [
            ("server", "Multiplayer server"),
            ("client", "Factorio"),
            ("llama", "Local model"),
            ("mcp", "Game connection"),
            ("dashboard", "Dashboard"),
        ]:
            line = ttk.Frame(frame, padding=(0, 9))
            line.pack(fill="x")
            ttk.Label(line, text=title, width=22).pack(side="left")
            self.labels[key] = tk.StringVar(value="Not checked")
            ttk.Label(line, textvariable=self.labels[key], wraplength=490).pack(side="left")
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=12)
        self.start_button = ttk.Button(
            buttons, text="Start / attach everything", command=self.start, style="Accent.TButton"
        )
        self.start_button.pack(side="left")
        ttk.Button(
            buttons, text="Emergency Stop", command=self.emergency_stop, style="Danger.TButton"
        ).pack(side="left", padx=(10, 0))
        self.stop_button = ttk.Button(
            buttons, text="Stop launcher-owned services", command=self.stop
        )
        self.stop_button.pack(side="left", padx=10)
        self.note = tk.StringVar(
            value="AI Helper is the default. Full Autonomy stays locked. Attached services stay under your control."
        )
        ttk.Label(frame, textvariable=self.note, wraplength=720).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.pump)

    def choose(self):
        path = filedialog.askopenfilename(
            title="Choose AutoEngineer setup", filetypes=[("Setup JSON", "*.json")]
        )
        if path:
            self.profile.set(path)

    def start(self):
        if self.supervisor is None:
            try:
                self.supervisor = self.Supervisor(
                    self.Profile(self.profile.get()), lambda k, v: self.events.put((k, v))
                )
            except Exception:
                self.note.set(
                    "Setup is incomplete. Choose a valid isolated test profile; see launcher setup instructions."
                )
                return
        self.supervisor.cancel.clear()
        self.start_button.configure(state="disabled")

        def work():
            try:
                self.supervisor.start_all()
            except Exception:
                pass
            finally:
                self.events.put(("idle", ""))

        threading.Thread(target=work, daemon=True).start()

    def emergency_stop(self):
        if self.supervisor is None:
            return
        self.supervisor.cancel.set()
        self.note.set("Stopping AI; the test game stays open...")

        def work():
            try:
                self.supervisor.request_dashboard_stop()
                self.events.put(
                    ("halted", "AI/dashboard stopped. Test game and model remain open.")
                )
            except Exception:
                self.events.put(
                    ("error", "Stop not confirmed; inspect the dashboard and test game.")
                )

        threading.Thread(target=work, daemon=True).start()

    def stop(self, confirmed=False):
        if self.supervisor is None:
            if self.closing:
                self.root.destroy()
            return
        if not confirmed and not messagebox.askyesno(
            "Stop services?",
            "Stop the AI/dashboard first, save and close any test server started here, and close the client/model started here? Pre-existing services are left running.",
        ):
            return
        self.start_button.configure(state="disabled")
        self.note.set("Stopping safely...")

        def work():
            try:
                self.supervisor.stop_owned(include_game=True)
                self.supervisor.release()
                self.events.put(
                    (
                        "stopped",
                        "Launcher-owned services stopped. Attached services were left running.",
                    )
                )
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def close(self):
        if self.supervisor and not messagebox.askyesno(
            "Close launcher?",
            "Stop launcher-owned services safely and close? Attached services will remain running.",
        ):
            return
        self.closing = True
        self.stop(confirmed=True)

    def pump(self):
        if (
            self.supervisor
            and time.monotonic() - self.last_health > 3
            and not self.health_busy
            and not self.closing
        ):
            self.last_health = time.monotonic()
            self.health_busy = True

            def health():
                try:
                    self.supervisor.refresh_health()
                finally:
                    self.health_busy = False

            threading.Thread(target=health, daemon=True).start()
        while not self.events.empty():
            key, value = self.events.get()
            if key in self.labels:
                self.labels[key].set(value)
            elif key == "error":
                self.note.set(value)
                self.closing = False
            elif key == "halted":
                self.note.set(value)
                self.labels["dashboard"].set("Stopped by Emergency Stop")
                self.start_button.configure(state="normal")
            elif key == "idle":
                self.start_button.configure(state="normal")
            elif key == "stopped":
                self.note.set(value)
                self.start_button.configure(state="normal")
                if self.closing:
                    self.root.destroy()
                    return
        self.root.after(100, self.pump)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--component",
        choices=["dashboard", "dashboard_observer", "supervised_agent", "backend_check"],
    )
    parser.add_argument("--profile")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.component == "backend_check":
        from autoengineer_config import mcp_parameters
        from dispatch_boundary import DispatchBoundary
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        from mode_policy import ModePolicy

        async def check():
            async with stdio_client(mcp_parameters()) as (r, w):
                async with ClientSession(r, w) as raw:
                    await raw.initialize()
                    await DispatchBoundary(raw, policy=ModePolicy("helper")).verify()
            print("POLICY_8_VERIFIED", flush=True)

        asyncio.run(check())
        return
    if args.component == "dashboard":
        dashboard_component()
        return
    if args.component == "dashboard_observer":
        import dashboard_observer

        asyncio.run(dashboard_observer.main())
        return
    if args.component == "supervised_agent":
        import supervised_agent

        asyncio.run(supervised_agent.main())
        return
    if args.check:
        from launcher_services import Profile

        profile = Profile(args.profile)
        result = {
            "setup_valid": True,
            "profile": profile.identity,
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        if args.report:
            Path(args.report).write_text(json.dumps(result))
        return
    root = tk.Tk()
    Launcher(root, args.profile)
    root.mainloop()


if __name__ == "__main__":
    main()
