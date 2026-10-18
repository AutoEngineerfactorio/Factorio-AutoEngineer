"""Read-only Tk map and inventory; no game connections or action callbacks."""
import time
import tkinter as tk
from tkinter import ttk


def project(position, center, width, height, radius):
    scale = min(width, height) / (2 * radius)
    return width/2 + (position['x']-center['x'])*scale, height/2 + (position['y']-center['y'])*scale


class LiveView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.last = None
        self.received = None
        self.available = False
        self.status = tk.StringVar(value='Start a supervised session to view live data')
        self.zoom = tk.StringVar(value='60')
        ttk.Label(self, textvariable=self.status).pack(anchor='w', padx=8, pady=4)
        controls = ttk.Frame(self); controls.pack(fill='x', padx=8)
        ttk.Label(controls, text='Map radius (tiles):').pack(side='left')
        zoom = ttk.Combobox(controls, textvariable=self.zoom, values=['24', '60', '120'], state='readonly', width=5)
        zoom.pack(side='left', padx=6); zoom.bind('<<ComboboxSelected>>', lambda _: self.draw())
        ttk.Label(controls, text='Player: cyan | Resources: green | Visited: gray | Failed: red | Objective: gold | Proposal: orange').pack(side='left')
        body = ttk.Frame(self); body.pack(fill='both', expand=True, padx=8, pady=6)
        self.canvas = tk.Canvas(body, background='#14212b', highlightthickness=0, width=590, height=260)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.draw())
        inventory = ttk.Frame(body); inventory.pack(side='left', fill='both', padx=(10, 0))
        self.inventory_status = tk.StringVar(value='Main inventory: waiting')
        ttk.Label(inventory, textvariable=self.inventory_status).pack(anchor='w')
        self.items = ttk.Treeview(inventory, columns=('quality', 'count'), height=9)
        self.items.heading('#0', text='Item'); self.items.column('#0', width=130)
        self.items.heading('quality', text='Quality'); self.items.column('quality', width=75)
        self.items.heading('count', text='Count'); self.items.column('count', width=60, anchor='e')
        self.items.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(inventory, orient='vertical', command=self.items.yview)
        scrollbar.pack(side='right', fill='y'); self.items.configure(yscrollcommand=scrollbar.set)

    def reset(self):
        self.last = None; self.received = None; self.available = False
        self.status.set('Waiting for live data'); self.inventory_status.set('Main inventory: waiting')
        self.items.delete(*self.items.get_children()); self.draw()

    def update_frame(self, data):
        if data['status'] != 'ok':
            self.available = False
            return
        # A surface change must not overlay old surface markers.
        if self.last is not None and self.last['surface'] != data['surface']:
            for key in ('visited', 'failed', 'resources'): data[key] = []
            data['objective'] = data['proposal'] = None
        self.last = data; self.received = time.monotonic(); self.available = True
        self.items.delete(*self.items.get_children())
        for item in sorted(data['inventory'], key=lambda i: (i['name'], i['quality'])):
            self.items.insert('', 'end', text=item['name'], values=(item['quality'], item['count']))
        self.inventory_status.set('Main inventory' + (' (partial)' if data['truncated'] else '') if data['inventory_available'] else 'Main inventory unavailable')
        self.draw()

    def freshness(self, running):
        if self.last is None: return
        age = time.monotonic()-self.received
        state = 'Live' if running and self.available and age <= 3 else 'Stale' if running else 'Session ended; last snapshot'
        resource_age = self.last.get('resource_age_seconds')
        resource_note = f' | resources {resource_age+age:.1f}s old' if resource_age is not None else ''
        self.status.set(f"{state} | {self.last['surface']} | tick {self.last['tick']} | {age:.1f}s old{resource_note} | observed markers, not terrain")

    def draw(self):
        self.canvas.delete('all')
        if self.last is None:
            self.canvas.create_text(15, 15, anchor='nw', fill='white', text='Waiting for observed map data')
            return
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        center = self.last['position']; radius = float(self.zoom.get())
        def location(p): return project(p, center, width, height, radius)
        for delta in range(-int(radius), int(radius)+1, 10):
            x, _ = location({'x': center['x']+delta, 'y': center['y']})
            _, y = location({'x': center['x'], 'y': center['y']+delta})
            self.canvas.create_line(x, 0, x, height, fill='#243541')
            self.canvas.create_line(0, y, width, y, fill='#243541')
        for key, color, size in [('visited', '#65717a', 2), ('failed', '#ef6666', 5), ('resources', '#83d897', 5)]:
            for marker in self.last[key]:
                x, y = location(marker)
                if not 0 <= x <= width or not 0 <= y <= height: continue
                self.canvas.create_oval(x-size, y-size, x+size, y+size, fill=color, outline='')
                if key == 'resources': self.canvas.create_text(x+7, y, text=marker['name'], fill=color, anchor='w')
        for key, color in [('objective', '#ffda65'), ('proposal', '#ff9c5c')]:
            marker = self.last[key]
            if marker is not None:
                x, y = location(marker)
                if 0 <= x <= width and 0 <= y <= height:
                    self.canvas.create_line(width/2, height/2, x, y, fill=color, dash=(4, 4))
                    self.canvas.create_rectangle(x-5, y-5, x+5, y+5, outline=color, width=2)
        x, y = width/2, height/2
        self.canvas.create_polygon(x, y-8, x+6, y+6, x-6, y+6, fill='#5ed7f5')
        self.canvas.create_text(8, height-8, anchor='sw', fill='white', text=f"Player {center['x']:.2f}, {center['y']:.2f} | N up | 10-tile grid")
