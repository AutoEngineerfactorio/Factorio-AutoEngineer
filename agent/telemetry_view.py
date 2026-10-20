"""Read-only production-flow and electric-network telemetry graphs."""

import time
import tkinter as tk
from tkinter import scrolledtext, ttk

POWER_HISTORY_SECONDS = 120
POWER_HISTORY_POINTS = 180


class TelemetryView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.model = None
        self.power_history = {}
        self.power_last_tick = {}
        self.power_current = set()
        self.last_tick = None
        self.last_progress_at = None
        self.status = tk.StringVar(value="Waiting for production and power telemetry")
        self.production_target = tk.StringVar()
        self.production_rate_unit = tk.StringVar(value="/s")
        self.power_network = tk.StringVar()
        ttk.Label(self, textvariable=self.status, style="Section.TLabel").pack(
            anchor="w", pady=(0, 6)
        )
        charts = ttk.Panedwindow(self, orient="horizontal")
        charts.pack(fill="both", expand=True)

        production_frame = ttk.LabelFrame(charts, text="PRODUCTION FLOWS", padding=8)
        charts.add(production_frame, weight=3)
        controls = ttk.Frame(production_frame)
        controls.pack(fill="x", pady=(0, 4))
        ttk.Label(controls, text="Observed prototype:").pack(side="left")
        self.production_selector = ttk.Combobox(
            controls, textvariable=self.production_target, state="readonly", width=32
        )
        self.production_selector.pack(side="left", padx=6)
        self.production_selector.bind(
            "<<ComboboxSelected>>", lambda _event: self.draw_production()
        )
        ttk.Label(controls, text="Rate:").pack(side="left", padx=(10, 0))
        unit_selector = ttk.Combobox(
            controls, textvariable=self.production_rate_unit,
            values=("/s", "/min"), state="readonly", width=6
        )
        unit_selector.pack(side="left", padx=4)
        unit_selector.bind("<<ComboboxSelected>>", lambda _event: self.draw_production())
        self.production_canvas = tk.Canvas(
            production_frame, background="#171b20", height=250, highlightthickness=0
        )
        self.production_canvas.pack(fill="both", expand=True)
        self.production_canvas.bind("<Configure>", lambda _event: self.draw_production())
        self.production_legend = tk.StringVar(
            value="Production orange · consumption blue · items/sec (2s averages)"
        )
        ttk.Label(
            production_frame, textvariable=self.production_legend, style="Muted.TLabel"
        ).pack(anchor="w")

        power_frame = ttk.LabelFrame(charts, text="POWER NETWORK", padding=8)
        charts.add(power_frame, weight=2)
        power_controls = ttk.Frame(power_frame)
        power_controls.pack(fill="x", pady=(0, 4))
        ttk.Label(power_controls, text="Network:").pack(side="left")
        self.power_selector = ttk.Combobox(
            power_controls, textvariable=self.power_network, state="readonly", width=22
        )
        self.power_selector.pack(side="left", padx=6)
        self.power_selector.bind(
            "<<ComboboxSelected>>", lambda _event: self.draw_power()
        )
        self.power_canvas = tk.Canvas(
            power_frame, background="#171b20", height=250, highlightthickness=0
        )
        self.power_canvas.pack(fill="both", expand=True)
        self.power_canvas.bind("<Configure>", lambda _event: self.draw_power())
        self.power_status = tk.StringVar(value="No electric network sample")
        ttk.Label(
            power_frame, textvariable=self.power_status, style="Muted.TLabel", wraplength=500
        ).pack(anchor="w")

        recommendation_frame = ttk.LabelFrame(
            self, text="BOTTLENECK CANDIDATES · EVIDENCE-BASED HINTS", padding=8
        )
        recommendation_frame.pack(fill="x", pady=(8, 0))
        self.recommendations = scrolledtext.ScrolledText(
            recommendation_frame, height=7, wrap="word", state="disabled"
        )
        self.recommendations.pack(fill="both", expand=True)
        ttk.Label(
            self,
            text=(
                "Production rates are force/surface flow statistics, not machine-level rates. "
                "Power is sampled from visible own electric networks near the player. "
                "Candidate explanations are not proof of a shortage or fault. Read-only; no game writes."
            ),
            style="Muted.TLabel",
            wraplength=1200,
        ).pack(anchor="w", pady=(6, 0))

    def update_frame(self, frame):
        if not isinstance(frame, dict) or frame.get("status") != "ok":
            self.status.set("Telemetry unavailable · last graph sample may be stale")
            self.power_status.set("Power telemetry unavailable")
            self.power_current = set()
            self.draw_production()
            self.draw_power()
            return

        from production_telemetry import telemetry_view_model

        telemetry = frame.get("telemetry")
        self.model = telemetry_view_model(telemetry)
        now = time.monotonic()
        tick = frame["tick"]
        if self.last_tick is None or tick > self.last_tick:
            self.last_tick = tick
            self.last_progress_at = now
        elif tick < self.last_tick:
            self.power_history.clear()
            self.power_last_tick.clear()
            self.last_tick = tick
            self.last_progress_at = now
        status_text = self.model["status_text"]
        if self.last_progress_at is not None and now - self.last_progress_at > 5:
            status_text += " · game tick has not advanced for 5s; telemetry may be stale"
        self.status.set(status_text)
        self._update_production_targets()
        self._record_power(frame["tick"])
        self._update_power_targets()
        self._show_recommendations()
        self.draw_production()
        self.draw_power()

    def _update_production_targets(self):
        if self.model is None:
            return
        choices = {}
        for material_type, rows in (
            ("item", self.model["items"]),
            ("fluid", self.model["fluids"]),
        ):
            for row in rows:
                label = f"{material_type}:{row['name']}"
                choices[label] = row
        self.production_rows = choices
        labels = list(choices)
        self.production_selector.configure(values=labels)
        if self.production_target.get() not in choices:
            self.production_target.set(labels[0] if labels else "")

    def _record_power(self, tick):
        if self.model is None:
            return
        now = time.monotonic()
        current = set()
        for network in self.model["networks"]:
            network_id = network["network_id"]
            current.add(network_id)
            previous_tick = self.power_last_tick.get(network_id, -1)
            if tick < previous_tick:
                self.power_history[network_id] = []
                previous_tick = -1
            history = self.power_history.setdefault(network_id, [])
            if tick > previous_tick:
                if network.get("source") == "legacy_statistics":
                    if network["history_available"]:
                        history.append((
                            now,
                            network["observed_output"] * 60,
                            network["observed_input"] * 60,
                            None,
                        ))
                else:
                    history.append((
                        now,
                        network["maximum_production"] * 60,
                        network["maximum_consumption"] * 60,
                        network["consumption_satisfaction"],
                    ))
                self.power_last_tick[network_id] = tick
        self.power_current = (
            current if self.model["power_status"] in ("ok", "partial") else set()
        )
        cutoff = now - POWER_HISTORY_SECONDS
        for network_id, history in list(self.power_history.items()):
            recent = [point for point in history if point[0] >= cutoff]
            if recent:
                self.power_history[network_id] = recent[-POWER_HISTORY_POINTS:]
            else:
                self.power_history.pop(network_id)
                self.power_last_tick.pop(network_id, None)
        network_rows = self.model["networks"]
        if network_rows:
            selected = next(
                (row for row in network_rows
                 if str(row["network_id"]) == self.power_network.get()),
                network_rows[0],
            )
            if selected.get("source") == "legacy_statistics":
                if selected["history_available"]:
                    from production_telemetry import format_power
                    self.power_status.set(
                        f"Network {selected['network_id']} | Factorio 2.0 historical "
                        f"electricity input {format_power(selected['observed_input'] * 60)} "
                        f"/ output {format_power(selected['observed_output'] * 60)} "
                        f"(1-minute precision, measured average) | "
                        "Maximum capacity, satisfaction and accumulator state unknown"
                    )
                else:
                    self.power_status.set(
                        f"Network {selected['network_id']} visible | "
                        "Factorio 2.0 historical electricity flow not recorded yet; "
                        "capacity, consumption satisfaction and stored energy unknown"
                    )
            else:
                from production_telemetry import power_rate_display
                rates = power_rate_display(selected)
                self.power_status.set(
                    f"Network {selected['network_id']} | Generation {rates['production']} "
                    f"| Load {rates['consumption']} | Energy use "
                    f"{rates['energy_per_second']}/s; {rates['energy_per_minute_at_current_rate']}/min "
                    f"(at current load, 60 ticks/s) | Satisfaction "
                    f"{selected['consumption_satisfaction']:.1%} | "
                    f"{len(network_rows)} visible network(s)"
                    + (" | partial network list" if self.model["power_partial"] else "")
                )
        else:
            self.power_status.set(
                self.model.get("power_reason") or "No visible own network telemetry"
            )

    def _update_power_targets(self):
        histories = sorted(self.power_history)
        labels = [str(network_id) for network_id in histories]
        self.power_selector.configure(values=labels)
        if self.power_network.get() not in labels:
            self.power_network.set(labels[0] if labels else "")

    def _show_recommendations(self):
        if self.model is None:
            return
        self.recommendations.configure(state="normal")
        self.recommendations.delete("1.0", "end")
        for row in self.model["recommendations"]:
            self.recommendations.insert(
                "end", f"{row['severity'].upper()}  {row['title']}\n{row['detail']}\n\n"
            )
        self.recommendations.configure(state="disabled")

    @staticmethod
    def _draw_lines(canvas, series, legend, empty_text):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 100)
        height = max(canvas.winfo_height(), 100)
        left, right, top, bottom = 48, width - 12, 12, height - 30
        if not series or not any(values for _label, values, _color in series):
            canvas.create_text(
                width / 2, height / 2, text=empty_text, fill="#c6cbd0",
                width=width - 40,
            )
            return
        max_value = max(
            (max(values) for _label, values, _color in series if values),
            default=0,
        )
        max_value = max(max_value, 1)
        canvas.create_line(left, top, left, bottom, fill="#65717d")
        canvas.create_line(left, bottom, right, bottom, fill="#65717d")
        for fraction in (0, .25, .5, .75, 1):
            y = bottom - (bottom - top) * fraction
            canvas.create_line(left, y, right, y, fill="#303841")
            canvas.create_text(
                left - 5, y, text=f"{max_value * fraction:.1f}",
                fill="#aeb8c2", anchor="e",
            )
        for name, values, color in series:
            if not values:
                continue
            points = []
            for index, value in enumerate(values):
                x = left + (right - left) * index / max(len(values) - 1, 1)
                y = bottom - (bottom - top) * value / max_value
                points.extend((x, y))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, smooth=False)
        canvas.create_text(
            left + 4, top + 4, anchor="nw", text=legend, fill="#d5dbe1"
        )

    def draw_production(self):
        target = getattr(self, "production_target", None)
        choices = getattr(self, "production_rows", {})
        if target is None or target.get() not in choices:
            self._draw_lines(
                self.production_canvas, [], "", "No bounded production series available"
            )
            return
        from production_telemetry import convert_flow_rate
        row = choices[target.get()]
        interval = "second" if self.production_rate_unit.get() == "/s" else "minute"
        output = [convert_flow_rate(x, interval) for x in row["output"]]
        input_values = [convert_flow_rate(x, interval) for x in row["input"]]
        unit = "items" if target.get().startswith("item:") else "fluid units"
        suffix = self.production_rate_unit.get()
        produced = output[-1] if output else 0.0
        consumed = input_values[-1] if input_values else 0.0
        self.production_legend.set(
            f"Produced {produced:,.2f} {unit}{suffix} · "
            f"Consumed {consumed:,.2f} {unit}{suffix} · "
            "orange production / blue consumption · 2-second sample averages"
        )
        self._draw_lines(
            self.production_canvas,
            [
                ("production", output, "#e6a44e"),
                ("consumption", input_values, "#68aee0"),
            ],
            f"{target.get()} · units{self.production_rate_unit.get()} · 2-minute history (2s bins)",
            "No samples",
        )

    def draw_power(self):
        network_text = getattr(self, "power_network", None)
        histories = getattr(self, "power_history", {})
        if network_text is None or not network_text.get().isdigit():
            reason = "Power telemetry unavailable"
            if (self.model and self.model["networks"]
                    and self.model["networks"][0].get("source") == "legacy_statistics"):
                reason = "Visible Factorio 2.0 electric network; historical flow not yet recorded"
            self._draw_lines(self.power_canvas, [], "", reason)
            return
        network_id = int(network_text.get())
        history = histories.get(network_id, [])
        current = "latest sample unavailable · " if network_id not in self.power_current else ""
        self._draw_lines(
            self.power_canvas,
            [
                ("generation/output", [row[1] if row[1] is not None else 0
                                        for row in history], "#e6a44e"),
                ("load/input", [row[2] if row[2] is not None else 0
                                  for row in history], "#68aee0"),
            ],
            f"{current}Network {network_text.get()} · output orange · input blue · watts "
            "(unknown history is not zero)",
            "Waiting for advancing game ticks",
        )
