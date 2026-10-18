"""Factorio AutoEngineer supervised dashboard (Windows, Python 3.12, Tkinter).

Runs the existing supervised_agent.py as a child process. No automatic approvals.
The dashboard does not directly access Factorio, RCON, or MCP.
"""
import os
import json
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from session_safety import PROMPT
from navigation_objective import Objective
from dashboard_feed import PREFIX, parse_frame
from dashboard_view import LiveView
from verified_operations import validate_operation

AGENT = Path(__file__).resolve().parent / "supervised_agent.py"

class Dashboard:
    def __init__(self, root):
        self.root = root
        root.title("Factorio AutoEngineer | Supervised Control")
        root.geometry("1200x820")
        root.minsize(1050, 720)
        self.proc = None
        self.observer = None
        self.q = queue.Queue()
        self.waiting_for_approval = False
        self.stop_requested = False
        self.stop_confirmed = False
        self.closing = False
        self.latest_proposal = "No action proposed yet."
        self.objective = tk.StringVar(value=os.environ.get('AUTOENGINEER_OBJECTIVE', ''))
        self.task = tk.StringVar(value='Navigate')
        self.operation_name = tk.StringVar(value='iron-ore')
        self.operation_count = tk.StringVar(value='1')
        self.status = tk.StringVar(value="Idle")
        self.position = tk.StringVar(value="Unknown")
        self.cycle = tk.StringVar(value="-")
        self.verification = tk.StringVar(value="-")
        self.build_ui()
        self.root.after(80, self.process_events)
        self.root.after(100, self.start_observer)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        header = ttk.Frame(self.root, padding=(18, 15))
        header.pack(fill="x")
        ttk.Label(header, text="FACTORIO AUTOENGINEER", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(header, text="Supervised agent - approval required for every action").pack(anchor="w", pady=(3, 0))
        stats = ttk.Frame(self.root, padding=(18, 4))
        stats.pack(fill="x")
        for title, var in (("STATUS", self.status), ("CYCLE", self.cycle), ("PLAYER POSITION", self.position), ("LAST VERIFICATION", self.verification)):
            cell = ttk.LabelFrame(stats, text=title, padding=10)
            cell.pack(side="left", expand=True, fill="x", padx=(0, 8))
            ttk.Label(cell, textvariable=var, wraplength=205, font=("Segoe UI", 10, "bold")).pack(anchor="w")

        proposal_box = ttk.LabelFrame(self.root, text="AI proposal / decision", padding=10)
        proposal_box.pack(fill="x", padx=18, pady=10)
        self.proposal_label = ttk.Label(proposal_box, text=self.latest_proposal, wraplength=960, justify="left")
        self.proposal_label.pack(fill="x")

        objective_box = ttk.Frame(self.root, padding=(18, 0, 18, 10))
        objective_box.pack(fill='x')
        ttk.Label(objective_box, text='Objective (optional resource name or x,y):').pack(side='left')
        ttk.Entry(objective_box, textvariable=self.objective, width=30).pack(side='left', padx=10)
        tasks = ttk.Frame(self.root, padding=(18, 0, 18, 8)); tasks.pack(fill='x')
        ttk.Label(tasks, text='Session action:').pack(side='left')
        task = ttk.Combobox(tasks, textvariable=self.task, values=['Navigate', 'Mine', 'Craft'], state='readonly', width=12)
        task.pack(side='left', padx=8)
        task.bind('<<ComboboxSelected>>', lambda _: self.operation_name.set('iron-gear-wheel' if self.task.get() == 'Craft' else 'iron-ore'))
        ttk.Combobox(tasks, textvariable=self.operation_name, values=['iron-ore','copper-ore','coal','stone','iron-gear-wheel','copper-cable'], width=20).pack(side='left')
        ttk.Label(tasks, text='Batch (1–3):').pack(side='left', padx=(12, 4))
        ttk.Spinbox(tasks, textvariable=self.operation_count, from_=1, to=3, width=4).pack(side='left')
        controls = ttk.Frame(self.root, padding=(18, 0))
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="Start supervised session", command=self.start)
        self.start_button.pack(side="left", padx=(0, 10))
        self.approve_button = ttk.Button(controls, text="Approve action", command=lambda: self.answer("y"), state="disabled")
        self.approve_button.pack(side="left", padx=(0, 10))
        self.reject_button = ttk.Button(controls, text="Reject / next proposal", command=lambda: self.answer("n"), state="disabled")
        self.reject_button.pack(side="left", padx=(0, 10))
        self.stop_button = ttk.Button(controls, text="Stop session", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")

        tabs = ttk.Notebook(self.root)
        tabs.pack(fill='both', expand=True, padx=18, pady=10)
        self.live_view = LiveView(tabs)
        tabs.add(self.live_view, text='Live map and inventory')
        activity = ttk.Frame(tabs); tabs.add(activity, text='Agent activity')
        self.log = scrolledtext.ScrolledText(activity, state="disabled", font=("Consolas", 10), wrap="word")
        self.log.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        footer = ttk.Frame(self.root, padding=(18, 0, 18, 12))
        footer.pack(fill="x")
        ttk.Label(footer, text="Actions require approval. Stop clears movement, mining and unfinished agent-owned crafts.").pack(side="left")
        ttk.Button(footer, text="Clear log", command=self.clear_log).pack(side="right")

    def display_frame(self, value):
        try:
            frame=parse_frame(value)
            if frame['status']=='ok':
                if self.live_view.last and self.live_view.last['surface']!=frame['surface']:
                    self.display_markers={}
                frame.update(getattr(self,'display_markers',{}))
                self.position.set(f"{frame['position']['x']:.2f}, {frame['position']['y']:.2f}")
            self.live_view.update_frame(frame)
        except (ValueError,TypeError,KeyError,AttributeError):
            self.live_view.update_frame({'status':'unavailable'})

    def start_observer(self):
        if self.closing or self.observer is not None:return
        startup=subprocess.STARTUPINFO() if os.name=='nt' else None
        if startup:
            startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow=subprocess.SW_HIDE
        try:
            self.observer=subprocess.Popen([sys.executable,'-u',str(AGENT.with_name('dashboard_observer.py'))],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',errors='replace',cwd=str(AGENT.parent),startupinfo=startup)
            threading.Thread(target=self.read_output,args=(self.observer,),daemon=True).start()
        except OSError:
            self.live_view.update_frame({'status':'unavailable'})
            self.root.after(3000,self.start_observer)

    def close_display(self):
        self.closing=True
        p=self.observer
        if p and p.poll() is None:
            try:p.stdin.write('q\n');p.stdin.flush()
            except (OSError,ValueError):pass
            # Observer owns no gameplay; give its MCP transport time to close.
            self.root.after(100,lambda:self.finish_display_close(p,0))
        else:self.root.destroy()

    def finish_display_close(self,p,attempt):
        if p.poll() is not None:
            self.root.destroy();return
        if attempt>=70:
            if os.name=='nt':
                subprocess.Popen(['taskkill','/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW)
            else:p.terminate()
            self.root.destroy();return
        self.root.after(100,lambda:self.finish_display_close(p,attempt+1))

    def append(self, txt):
        self.log.configure(state="normal")
        self.log.insert("end", txt)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_approval(self, enabled):
        self.waiting_for_approval = enabled
        state = "normal" if enabled else "disabled"
        self.approve_button.configure(state=state)
        self.reject_button.configure(state=state)
        if enabled:
            self.status.set("Awaiting your approval")

    def start(self):
        if self.closing or self.proc is not None:
            return
        selected_objective = self.objective.get().strip()
        mode = self.task.get() if hasattr(self, 'task') else 'Navigate'
        if selected_objective and mode == 'Navigate':
            try:
                Objective(selected_objective)
            except ValueError as exc:
                messagebox.showerror('Invalid objective', str(exc))
                return
        child_env = dict(os.environ)
        child_env.pop('AUTOENGINEER_OPERATION', None)
        child_env.pop('AUTOENGINEER_OBJECTIVE', None)
        if selected_objective:
            child_env['AUTOENGINEER_OBJECTIVE'] = selected_objective
        if mode != 'Navigate':
            try:
                operation = validate_operation({'kind': mode.lower(), 'name': self.operation_name.get().strip(), 'count': int(self.operation_count.get())})
            except (ValueError, TypeError) as exc:
                messagebox.showerror('Invalid operation', str(exc)); return
            child_env['AUTOENGINEER_OPERATION'] = json.dumps(operation)
        if not AGENT.is_file():
            messagebox.showerror("Agent not found", f"Place dashboard next to:\n{AGENT}")
            return
        self.stop_requested = False
        self.stop_confirmed = False
        self.set_approval(False)
        self.status.set("Starting")
        self.cycle.set("-")
        self.verification.set("-")
        self.position.set("Unknown")
        # Live observation continues independently of AI session lifecycle.
        self.proposal_label.configure(text="Waiting for an action proposal...")
        self.append("\n========= New supervised session =========\n")
        try:
            startup = subprocess.STARTUPINFO() if os.name == "nt" else None
            if startup is not None:
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = subprocess.SW_HIDE
            self.proc = subprocess.Popen(
                [sys.executable, "-u", str(AGENT)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=0,
                cwd=str(AGENT.parent), startupinfo=startup,
                env=child_env,
            )
        except OSError as exc:
            self.status.set("Launch failed")
            messagebox.showerror("Launch failed", str(exc))
            return
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        p = self.proc
        threading.Thread(target=self.read_output, args=(p,), daemon=True).start()

    def read_output(self, proc):
        # Read one character at a time because input() prints its prompt
        # without a trailing newline. Detect that prompt before asking for approval.
        buffer = ""
        try:
            while True:
                ch = proc.stdout.read(1)
                if ch == "":
                    break
                buffer += ch
                if buffer.endswith(PROMPT):
                    self.q.put((proc, "line", buffer))
                    self.q.put((proc, "prompt", None))
                    buffer = ""
                elif ch == "\n":
                    self.q.put((proc, "line", buffer))
                    buffer = ""
                elif len(buffer) > 1048576:
                    self.q.put((proc, "line", buffer))
                    buffer = ""
            if buffer:
                self.q.put((proc, "line", buffer))
        except Exception as exc:
            self.q.put((proc, "line", f"\n[Dashboard output reader error: {exc}]\n"))
        finally:
            code = proc.wait()
            self.q.put((proc, "exit", code))

    def process_events(self):
        try:
            for _ in range(300):
                proc, kind, value = self.q.get_nowait()
                if proc is self.observer:
                    if kind == 'line' and value.startswith(PREFIX):
                        self.display_frame(value)
                    elif kind == 'exit':
                        self.observer = None
                        self.live_view.update_frame({'status':'unavailable'})
                        if not self.closing:self.root.after(3000,self.start_observer)
                    continue
                if proc is not self.proc:
                    continue
                if kind == "line":
                    if value.startswith(PREFIX):
                        # Agent frames add objective/proposal markers; observer owns live world data.
                        try:
                            f=parse_frame(value)
                            if f.get('status')=='ok':
                                self.display_markers={k:f[k] for k in ('visited','failed','resources','objective','proposal')}
                        except (ValueError,TypeError,KeyError):pass
                        continue
                    if value.strip() == "SAFETY_STOP_CONFIRMED":
                        self.stop_confirmed = True
                    self.append(value)
                    self.inspect_line(value)
                elif kind == "prompt":
                    if not self.stop_requested:
                        self.set_approval(True)
                elif kind == "exit":
                    self.set_approval(False)
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    if self.stop_confirmed:
                        self.status.set("Game-side stop acknowledged")
                    else:
                        self.status.set("Exited; game-side stop unconfirmed")
                    self.append(f"\n[Agent process exited with code {value}]\n")
                    self.proc = None
                    if self.closing:
                        self.close_display()
                        return
        except queue.Empty:
            pass
        if hasattr(self, 'live_view'):
            self.live_view.freshness(self.observer is not None)
        self.root.after(80, self.process_events)

    def inspect_line(self, line):
        if self.stop_requested:
            return
        match = re.search(r"AI CYCLE\s+(\d+/\d+)", line)
        if match:
            self.cycle.set(match.group(1))
            self.status.set("Planning")
        if "Qwen proposes:" in line or 'Action proposed:' in line:
            self.proposal_label.configure(text="Reading proposed action...")
        if any(key in line for key in ('"action":', '"reason":', '"targetX":', '"targetY":', '"name":', '"count":')):
            current = self.proposal_label.cget("text")
            if current == "Reading proposed action...":
                current = ""
            self.proposal_label.configure(text=(current + line.strip() + "  ")[-900:])
        match = re.search(r"Final position:\s*(.+)", line)
        if match:
            self.position.set(match.group(1))
        if "Verified success:" in line:
            self.verification.set(line.split(":", 1)[-1].strip())
        if 'Verified operation:' in line:
            self.verification.set(line.split(':', 1)[-1].strip())
        if "Verification failed" in line:
            self.status.set("Verification failed")

    def answer(self, choice):
        p = self.proc
        if self.stop_requested or not self.waiting_for_approval or not p or p.poll() is not None:
            return
        self.set_approval(False)
        try:
            p.stdin.write(choice + "\n")
            p.stdin.flush()
            self.append(f"\n[You selected: {'Approve' if choice == 'y' else 'Reject'}]\n")
            self.status.set("Executing approved action" if choice == "y" else "Replanning")
        except (OSError, ValueError) as exc:
            self.append(f"\n[Could not send decision: {exc}]\n")

    def stop(self):
        p = self.proc
        if not p or p.poll() is not None:
            return
        if self.stop_requested:
            return
        self.stop_requested = True
        self.set_approval(False)
        self.status.set("Stopping")
        if p.stdin and not p.stdin.closed:
            try:
                p.stdin.write("q\n")
                p.stdin.flush()
            except (OSError, ValueError):
                pass
        # The controller's independent reader consumes q during any phase.
        # Allow bounded game-side stop, cancellation and transport cleanup first.
        threading.Thread(target=self.force_stop_after_delay, args=(p,), daemon=True).start()

    def force_stop_after_delay(self, p):
        try:
            p.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            self.q.put((p, "line", "\n[Forced termination fallback; game-side stop unconfirmed. Lease expiry is the fallback.]\n"))
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15, check=False)
            else:
                p.terminate()
        except Exception as exc:
            self.q.put((p, "line", f"\n[Stop failed: {exc}]\n"))

    def on_close(self):
        if self.proc is not None:
            if self.closing:
                return
            if not messagebox.askyesno("Exit dashboard", "Request a game-side stop and close after the controller exits?"):
                return
            self.closing = True
            self.start_button.configure(state="disabled")
            # The modal dialog runs a nested Tk event loop. The controller may
            # have exited (and its exit event been consumed) while it was open.
            # In that case there will be no later event to close the window.
            if self.proc is None or self.proc.poll() is not None:
                self.close_display()
                return
            self.stop()
            return
        self.close_display()

if __name__ == "__main__":
    app = tk.Tk()
    Dashboard(app)
    app.mainloop()
