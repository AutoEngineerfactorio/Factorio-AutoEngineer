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
from mode_policy import HELPER, SEMI, FULL, LABELS
from app_runtime import component_command
from factorio_theme import apply_theme, INSET, TEXT, AMBER

AGENT = Path(__file__).resolve().parent / "supervised_agent.py"

class Dashboard:
    def __init__(self, root):
        self.root = root
        apply_theme(root)
        root.title("Factorio AutoEngineer | Supervised Control")
        root.geometry("1480x960")
        root.minsize(1240, 820)
        self.current_mode = HELPER
        self.mode = tk.StringVar(value='AI Helper')
        self.mode_note = tk.StringVar(value='AI Helper: live observation only. Recipe and blueprint planning are future work.')
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
        self.sync_mode_controls()
        self.root.after(80, self.process_events)
        self.root.after(100, self.start_observer)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self):
        header=ttk.Frame(self.root,padding=(20,16,20,12));header.pack(fill='x')
        ttk.Label(header,text='AUTOENGINEER',style='Heading.TLabel').pack(side='left')
        ttk.Label(header,text='  /  FACTORY COMPANION',style='Muted.TLabel').pack(side='left',padx=8)
        ttk.Label(header,text='LOCAL CONTROL  /  HUMAN SUPERVISED',style='Badge.TLabel').pack(side='right')
        ttk.Separator(self.root).pack(fill='x',padx=20)
        modes=ttk.Frame(self.root,padding=(20,10,20,8));modes.pack(fill='x')
        ttk.Label(modes,text='OPERATING MODE',style='Section.TLabel').pack(side='left')
        self.mode_selector=ttk.Combobox(modes,textvariable=self.mode,values=list(LABELS),state='readonly',width=28)
        self.mode_selector.pack(side='left',padx=12)
        self.mode_selector.bind('<<ComboboxSelected>>',self.change_mode)
        ttk.Label(modes,textvariable=self.mode_note,style='Muted.TLabel',wraplength=700).pack(side='left')
        stats=ttk.Frame(self.root,padding=(20,0,20,10));stats.pack(fill='x')
        for title,var in (('AGENT STATUS',self.status),('CYCLE',self.cycle),('PLAYER POSITION',self.position),('LAST VERIFICATION',self.verification)):
            cell=ttk.LabelFrame(stats,text=title,padding=(12,9));cell.pack(side='left',expand=True,fill='both',padx=(0,8))
            ttk.Label(cell,textvariable=var,wraplength=270,style='Value.TLabel').pack(anchor='w')
        workspace=ttk.Panedwindow(self.root,orient='horizontal');workspace.pack(fill='both',expand=True,padx=20,pady=(0,10))
        tabs=ttk.Notebook(workspace);workspace.add(tabs,weight=5)
        self.live_view=LiveView(tabs);tabs.add(self.live_view,text='SURFACE & INVENTORY')
        activity=ttk.Frame(tabs);tabs.add(activity,text='ACTIVITY LOG')
        self.log=scrolledtext.ScrolledText(activity,state='disabled',font=('Consolas',10),wrap='word',background=INSET,foreground=TEXT,insertbackground=AMBER,relief='flat',borderwidth=0,padx=12,pady=12)
        self.log.pack(fill='both',expand=True,padx=6,pady=6)
        side=ttk.Frame(workspace,width=325,padding=(12,4,0,0));workspace.add(side,weight=1)
        ttk.Label(side,text='MISSION CONTROL',style='Section.TLabel').pack(anchor='w',pady=(5,10))
        objective_box=ttk.LabelFrame(side,text='OBJECTIVE',padding=12);objective_box.pack(fill='x',pady=(0,10))
        ttk.Label(objective_box,text='Resource name or x,y',style='Muted.TLabel').pack(anchor='w')
        ttk.Entry(objective_box,textvariable=self.objective,width=28).pack(fill='x',pady=(6,0))
        tasks=ttk.LabelFrame(side,text='SESSION TASK',padding=12);tasks.pack(fill='x',pady=(0,10))
        task=ttk.Combobox(tasks,textvariable=self.task,values=['Navigate','Mine','Craft'],state='readonly',width=25);task.pack(fill='x')
        task.bind('<<ComboboxSelected>>',lambda _:self.operation_name.set('iron-gear-wheel' if self.task.get()=='Craft' else 'iron-ore'))
        ttk.Combobox(tasks,textvariable=self.operation_name,values=['iron-ore','copper-ore','coal','stone','iron-gear-wheel','copper-cable'],width=25).pack(fill='x',pady=8)
        quantity=ttk.Frame(tasks);quantity.pack(fill='x')
        ttk.Label(quantity,text='Batch size  /  1–3',style='Muted.TLabel').pack(side='left')
        ttk.Spinbox(quantity,textvariable=self.operation_count,from_=1,to=3,width=4).pack(side='right')
        proposal_box=ttk.LabelFrame(side,text='PROPOSED ACTION',padding=12);proposal_box.pack(fill='x',pady=(0,10))
        self.proposal_label=ttk.Label(proposal_box,text=self.latest_proposal,wraplength=280,justify='left');self.proposal_label.pack(fill='x')
        controls=ttk.Frame(side);controls.pack(fill='x',pady=4)
        self.start_button=ttk.Button(controls,text='Start supervised session',command=self.start,style='Accent.TButton');self.start_button.pack(fill='x',pady=4)
        self.approve_button=ttk.Button(controls,text='Approve action',command=lambda:self.answer('y'),state='disabled',style='Approve.TButton');self.approve_button.pack(fill='x',pady=4)
        self.reject_button=ttk.Button(controls,text='Reject / next proposal',command=lambda:self.answer('n'),state='disabled');self.reject_button.pack(fill='x',pady=4)
        self.stop_button=ttk.Button(controls,text='EMERGENCY STOP',command=self.stop,state='disabled',style='Danger.TButton');self.stop_button.pack(fill='x',pady=(10,4))
        ttk.Label(side,text='Escape stops the active session.\nFresh approval per action.\nFive-tile movement limit.',style='Muted.TLabel',wraplength=290).pack(anchor='w',pady=10)
        footer=ttk.Frame(self.root,padding=(20,0,20,12));footer.pack(fill='x')
        ttk.Label(footer,text='Live observation stays on while the AI is idle.  /  Stop clears owned movement, mining and unfinished crafts.',style='Muted.TLabel').pack(side='left')
        ttk.Button(footer,text='Clear log',command=self.clear_log).pack(side='right')
        self.root.bind('<Escape>',lambda _:self.stop())

    def sync_mode_controls(self):
        semi=self.current_mode==SEMI
        if semi:
            if not self.start_button.winfo_manager():self.start_button.pack(side='top',before=self.approve_button,fill='x',pady=4)
            self.start_button.configure(state='normal' if self.proc is None and not self.closing else 'disabled')
        else:
            self.start_button.configure(state='disabled')
            self.start_button.pack_forget()
        if not semi:self.set_approval(False)

    def change_mode(self,event=None):
        requested=LABELS.get(self.mode.get())
        old_label=next(k for k,v in LABELS.items() if v==self.current_mode)
        if requested==FULL or requested is None:
            self.mode.set(old_label)
            messagebox.showinfo('Mode locked','Fully Autonomous is locked until acceptance tests pass.')
            return
        if requested==self.current_mode:return
        if requested==SEMI:
            if self.proc is not None or (self.stop_requested and not self.stop_confirmed):
                self.mode.set(old_label)
                messagebox.showinfo('Wait for safe stop','Wait for game-side stop acknowledgement before starting a new gameplay session.')
                return
            if not messagebox.askyesno('Enable supervised gameplay?','Semi-Autonomous permits approved movement, mining and crafting. Every action still requires approval. Enable it?'):
                self.mode.set(old_label);return
        self.current_mode=requested
        self.display_markers={}
        self.set_approval(False)
        if requested==HELPER:
            self.mode_note.set('AI Helper: live observation only. Recipe and blueprint planning are future work.')
            if self.proc is not None:self.stop()
        else:self.mode_note.set('Semi-Autonomous: fresh approval per action; five-tile limit; Stop always available.')
        self.sync_mode_controls()

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
            self.observer=subprocess.Popen(component_command('dashboard_observer'),
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',errors='replace',cwd=str(Path(sys.executable).parent if getattr(sys,'frozen',False) else AGENT.parent),startupinfo=startup)
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
        enabled = enabled and self.current_mode == SEMI and not self.stop_requested
        self.waiting_for_approval = enabled
        state = "normal" if enabled else "disabled"
        self.approve_button.configure(state=state)
        self.reject_button.configure(state=state)
        if enabled:
            self.status.set("Awaiting your approval")

    def start(self):
        if self.closing or self.proc is not None or self.current_mode != SEMI:
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
        child_env['AUTOENGINEER_MODE'] = SEMI
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
        if not getattr(sys,'frozen',False) and not AGENT.is_file():
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
                component_command('supervised_agent'),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=0,
                cwd=str(Path(sys.executable).parent if getattr(sys,'frozen',False) else AGENT.parent), startupinfo=startup,
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
                    if not self.stop_requested and self.current_mode == SEMI:
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
                    if hasattr(self,'mode_selector'):self.sync_mode_controls()
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
        if "Model proposes:" in line or "Qwen proposes:" in line or 'Action proposed:' in line:
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
        if self.current_mode != SEMI or self.stop_requested or not self.waiting_for_approval or not p or p.poll() is not None:
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
