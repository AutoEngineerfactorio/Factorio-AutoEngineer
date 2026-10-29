"""Read-only recipe and research catalog browser."""

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

from effective_yield import yield_of_part, yield_of_products
from recipe_feasibility import STATUS_LOCKED, assess_recipes
from recipe_material_planner import (
    format_material_plan,
    format_target_production,
    plan_product_materials,
    plan_target_production,
)

MAX_VISIBLE_RECIPES = 250


def _format_part(part):
    """Format one observed part with the mechanics it carries.

    The mechanics are shown next to the amount so a ranged, probabilistic,
    temperature-bound, quality-restricted or productivity-restricted part is
    never presented as a plain fixed amount.
    """
    entry = yield_of_part(part)
    amount = f"{part.get('amount', 0):g}"
    if entry.minimum is not None and entry.maximum is not None:
        if entry.minimum != entry.maximum:
            amount = f"{entry.minimum:g}-{entry.maximum:g}"
    details = []
    if entry.probability is not None:
        details.append(f"p={entry.probability * 100:g}%")
    temperature = part.get("temperature")
    if temperature is not None:
        details.append(f"{temperature:g} degC")
    low = part.get("minimum_temperature")
    high = part.get("maximum_temperature")
    if low is not None or high is not None:
        low_text = f"{low:g}" if low is not None else "any"
        high_text = f"{high:g}" if high is not None else "any"
        details.append(f"temperature {low_text}-{high_text} degC")
    quality_min = part.get("quality_min")
    quality_max = part.get("quality_max")
    if quality_min is not None or quality_max is not None:
        details.append(f"quality {quality_min or 'any'}..{quality_max or 'any'}")
    if part.get("quality_change") is not None:
        details.append(f"quality change {part['quality_change']:+g}")
    ignored = part.get("ignored_by_productivity")
    if ignored:
        details.append(f"{ignored:g} ignored by productivity")
    spoiled = part.get("percent_spoiled")
    if spoiled:
        details.append(f"{spoiled * 100:g}% spoiled")
    extra = part.get("extra_count_fraction")
    if extra:
        details.append(f"extra p={extra * 100:g}%")
    if not details:
        return amount
    return f"{amount} ({'; '.join(details)})"


def catalog_view_model(intelligence):
    capabilities = intelligence.get("capabilities")
    catalog_status = intelligence.get("catalog_status") or {}
    if not isinstance(capabilities, dict):
        # The empty model carries **every** key the full model carries, so a
        # consumer never has to guess whether a key is missing.
        return {
            "status": intelligence.get("reason", "Recipe/research catalog unavailable"),
            "metadata": "No same-tick capability snapshot",
            "recipes": [],
            "research": [],
            "unresearched_technologies": {},
            "unsupported_mechanics": [],
        }

    status = catalog_status.get("status")
    if status == "assembled" and capabilities.get("truncated"):
        catalog_note = (
            f"Recipe pages assembled, but snapshot data is truncated "
            f"({len(capabilities['recipes'])} recipes)"
        )
    elif status == "assembled":
        catalog_note = f"Complete catalog: {len(capabilities['recipes'])} recipes"
    elif status == "ok":
        total = catalog_status.get("total_count", "unknown")
        pages = catalog_status.get("total_pages", "unknown")
        catalog_note = (
            f"Partial catalog page {catalog_status.get('page', '?')} of {pages} "
            f"({total} total recipes)"
        )
    else:
        catalog_note = "Catalog completeness not established"

    recipes = []
    observed_research: set[str] = set(capabilities.get("research") or ())
    feasibility_by_name = assess_recipes(
        capabilities.get("recipes", []), observed_research
    )
    unsupported_mechanics: list[str] = []
    for recipe in capabilities.get("recipes", []):
        unlocks = recipe.get("unlock_technologies") or []
        if recipe.get("unlock_technologies") is None:
            unlock_summary = "Not reported"
        elif not unlocks:
            unlock_summary = "No unlock effect observed"
        else:
            unlock_summary = ", ".join(
                f"{unlock['name']} ({'researched' if unlock['researched'] else 'not researched'})"
                for unlock in unlocks
            )
        products = ", ".join(
            f"{_format_part(part)} {part['type']}:{part['name']}"
            for part in recipe["products"]
        )
        ingredients = ", ".join(
            f"{_format_part(part)} {part['type']}:{part['name']}"
            for part in recipe["ingredients"]
        ) or "(no ingredients reported)"
        feasibility = feasibility_by_name[recipe["name"]]
        availability = (
            "Hidden" if recipe["hidden"]
            else "Disabled" if not recipe["enabled"]
            else "Locked" if feasibility.status == STATUS_LOCKED
            else "Enabled"
        )
        # Factorio 2.1 recipes may declare several categories. The first is the
        # primary category; the rest are additional crafting categories.
        categories = list(recipe.get("categories") or [])
        if recipe["category"] and recipe["category"] not in categories:
            categories.insert(0, recipe["category"])
        # The observed yield mechanics decide whether the outputs of this
        # recipe are a fixed amount. An uncertain yield is reported, never
        # hidden and never presented as a plain number.
        part_yields = yield_of_products(recipe["products"])
        ingredient_yields = [
            yield_of_part(part) for part in recipe["ingredients"]
        ]
        yield_uncertain = any(
            entry.is_uncertain for entry in part_yields + ingredient_yields
        )
        for entry in part_yields + ingredient_yields:
            for reason in entry.reasons:
                if reason not in unsupported_mechanics:
                    unsupported_mechanics.append(reason)
        recipes.append({
            "name": recipe["name"],
            "availability": availability,
            "category": recipe["category"],
            "categories": categories,
            "crafting_time": recipe["crafting_time"],
            "ingredients": ingredients,
            "products": products,
            "unlock_summary": unlock_summary,
            "yield_uncertain": yield_uncertain,
            "feasibility_status": feasibility.status,
            "feasibility_reasons": list(feasibility.reasons),
            "blocked_by": list(feasibility.blocked_by),
            "search": " ".join([
                recipe["name"], recipe["category"], *categories, ingredients,
                products, availability, unlock_summary,
                *(unlock["name"] for unlock in unlocks),
                *(reason for entry in part_yields + ingredient_yields
                  for reason in entry.reasons),
            ]).casefold(),
            "recipe": recipe,
        })

    research = capabilities.get("research", [])
    # The backend reports researched technology names, and reports the
    # technology that unlocks each recipe with its researched/enabled state.
    # The union of those observed unlock technologies is therefore the set of
    # technologies this profile actually exposes. A technology that unlocks no
    # observed recipe is not reported and is not invented here.
    technology_states = {}
    for recipe in capabilities.get("recipes", []):
        for unlock in recipe.get("unlock_technologies") or []:
            name = unlock.get("name")
            if not name:
                continue
            state = technology_states.setdefault(name, {
                "name": name,
                "researched": bool(unlock.get("researched")),
                "enabled": bool(unlock.get("enabled")),
            })
            # A technology is researched if any observed source says so.
            if unlock.get("researched"):
                state["researched"] = True
    unresearched_technologies = {
        name: state for name, state in technology_states.items()
        if not state["researched"]
    }
    enabled_content = capabilities.get("enabled_content", [])
    if len(enabled_content) > 12:
        enabled_content_label = (
            ", ".join(enabled_content[:12]) + f", ... (+{len(enabled_content) - 12})"
        )
    else:
        enabled_content_label = ", ".join(enabled_content) or "not reported"
    source_fingerprint = capabilities.get("source_fingerprint", "not reported")
    mechanics = intelligence.get("mechanics", {})
    dimensions = mechanics.get("dimension_counts", {})
    coverage_note = (
        "Mechanics evidence: "
        f"{mechanics.get('categories_with_evidence', 0)}/"
        f"{mechanics.get('total_categories', 0)} categories have evidence; "
        f"{dimensions.get('observed', 0)} observed, "
        f"{dimensions.get('verified', 0)} verified, "
        f"{dimensions.get('regression_passed', 0)} regression-passed"
    )
    ready_note = (
        "Catalog observed; planning is enabled only for independently qualified profiles."
        if intelligence.get("planner_ready")
        else "Planning disabled: " + intelligence.get("reason", "capability checks incomplete")
    )
    metadata = (
        f"{capabilities['game_version']}  |  Force: {capabilities['force']}  |  "
        f"Surface: {capabilities['surface']}  |  Tick: {capabilities['tick']}\n"
        f"{catalog_note}  |  {len(research)} researched technologies observed\n"
        f"Unresearched recipe-unlocking technologies observed: "
        f"{len(unresearched_technologies)}\n"
        f"Enabled content: {enabled_content_label}"
        f" (profile kind: {intelligence.get('content_kind', 'unknown')})\n"
        f"Source change fingerprint: {source_fingerprint} (not authentication)\n"
        f"{coverage_note}"
    )
    if unsupported_mechanics:
        metadata += (
            f"\nObserved output mechanics that are not exactly modelled "
            f"({len(unsupported_mechanics)}): "
            + "; ".join(unsupported_mechanics[:4])
            + ("; ..." if len(unsupported_mechanics) > 4 else "")
        )
    return {
        "status": ready_note,
        "metadata": metadata,
        "recipes": recipes,
        "research": research,
        "unresearched_technologies": unresearched_technologies,
        "unsupported_mechanics": sorted(unsupported_mechanics),
    }


class RecipeResearchView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.model = catalog_view_model({})
        self.intelligence = {}
        self.status = tk.StringVar(value="Waiting for read-only game observation")
        self.metadata = tk.StringVar(value="No same-tick capability snapshot")
        self.search = tk.StringVar()
        self.product_target = tk.StringVar()
        self.target_amount = tk.StringVar(value="1")
        self.product_choices = {}
        self.recipe_detail_text = ""
        #: The rate unit used by the production target: "per_second" or
        #: "per_minute".
        self.rate_unit = tk.StringVar(value="per_second")
        self.target_rate = tk.StringVar(value="1")
        self.machine_speed = tk.StringVar(value="")
        self.machine_power_kw = tk.StringVar(value="")
        #: The queue that carries a finished catalog model from the worker
        #: thread back to the main thread.
        self._model_queue = queue.Queue()
        #: The generation counter discards a model that a newer observation
        #: has already superseded.
        self._model_generation = 0
        #: True while a model build runs, so a fast frame rate cannot start
        #: a second build.
        self._model_building = False
        #: The newest observation that arrived while a build was running.
        self._pending_intelligence = None
        ttk.Label(self, textvariable=self.status, style="Section.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        ttk.Label(
            self, textvariable=self.metadata, style="Muted.TLabel", justify="left"
        ).pack(anchor="w", pady=(0, 6))
        search = ttk.Frame(self)
        search.pack(fill="x", pady=(0, 6))
        ttk.Label(search, text="Filter recipes:").pack(side="left")
        entry = ttk.Entry(search, textvariable=self.search)
        entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.search.trace_add("write", lambda *_: self.populate_recipes())

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)
        recipe_frame = ttk.Frame(body)
        body.add(recipe_frame, weight=3)
        self.recipe_list = ttk.Treeview(
            recipe_frame,
            columns=("availability", "category", "output", "unlock"),
            show="tree headings",
            selectmode="browse",
        )
        self.recipe_list.heading("#0", text="Recipe")
        self.recipe_list.column("#0", width=200, anchor="w")
        for column, title, width in (
            ("availability", "State", 90),
            ("category", "Category", 130),
            ("output", "Products", 280),
            ("unlock", "Research unlock effect", 220),
        ):
            self.recipe_list.heading(column, text=title)
            self.recipe_list.column(column, width=width, anchor="w")
        self.recipe_list.pack(side="left", fill="both", expand=True)
        recipe_scroll = ttk.Scrollbar(
            recipe_frame, orient="vertical", command=self.recipe_list.yview
        )
        recipe_scroll.pack(side="right", fill="y")
        self.recipe_list.configure(yscrollcommand=recipe_scroll.set)
        self.recipe_list.bind("<<TreeviewSelect>>", self.show_recipe)

        details_frame = ttk.Frame(body, padding=(8, 0, 0, 0))
        body.add(details_frame, weight=2)
        ttk.Label(details_frame, text="RECIPE DETAILS", style="Section.TLabel").pack(
            anchor="w"
        )
        plan_controls = ttk.Frame(details_frame)
        plan_controls.pack(fill="x", pady=(4, 4))
        ttk.Label(plan_controls, text="Target:").pack(side="left")
        self.product_selector = ttk.Combobox(
            plan_controls, textvariable=self.product_target, state="readonly", width=28
        )
        self.product_selector.pack(side="left", fill="x", expand=True, padx=(4, 6))
        ttk.Label(plan_controls, text="Amount:").pack(side="left")
        ttk.Entry(plan_controls, textvariable=self.target_amount, width=8).pack(
            side="left", padx=(4, 6)
        )
        self.plan_button = ttk.Button(
            plan_controls, text="Plan materials", command=self.show_material_plan
        )
        self.plan_button.pack(side="left")

        rate_controls = ttk.Frame(details_frame)
        rate_controls.pack(fill="x", pady=(0, 4))
        ttk.Label(rate_controls, text="Target rate:").pack(side="left")
        ttk.Entry(rate_controls, textvariable=self.target_rate, width=9).pack(
            side="left", padx=(4, 6)
        )
        self.rate_unit_box = ttk.Combobox(
            rate_controls, textvariable=self.rate_unit, state="readonly", width=12
        )
        self.rate_unit_box.configure(values=("per_second", "per_minute"))
        self.rate_unit_box.pack(side="left")
        ttk.Label(rate_controls, text="Machine speed:").pack(side="left", padx=(10, 0))
        ttk.Entry(rate_controls, textvariable=self.machine_speed, width=8).pack(
            side="left", padx=(4, 6)
        )
        ttk.Label(rate_controls, text="Machine kW:").pack(side="left")
        ttk.Entry(rate_controls, textvariable=self.machine_power_kw, width=8).pack(
            side="left", padx=(4, 6)
        )
        self.production_button = ttk.Button(
            rate_controls, text="Plan production", command=self.show_production_plan
        )
        self.production_button.pack(side="left")
        self.details = scrolledtext.ScrolledText(
            details_frame, height=12, wrap="word", state="disabled"
        )
        self.details.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Label(
            details_frame, text="RESEARCHED TECHNOLOGIES (OBSERVED)", style="Section.TLabel"
        ).pack(anchor="w")
        self.research_list = tk.Listbox(details_frame, height=8, exportselection=False)
        self.research_list.pack(fill="both", expand=True, pady=(4, 0))
        ttk.Label(
            details_frame,
            text="UNRESEARCHED RECIPE-UNLOCKING TECHNOLOGIES (OBSERVED)",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(8, 0))
        self.unresearched_list = tk.Listbox(
            details_frame, height=6, exportselection=False
        )
        self.unresearched_list.pack(fill="both", expand=True, pady=(4, 0))
        ttk.Label(
            self,
            text=(
                "Read-only catalog. Unlock effects do not prove prerequisites or buildability. "
                "Machine compatibility and production feasibility are not inferred. "
                "No gameplay writes."
            ),
            style="Muted.TLabel",
            wraplength=1100,
        ).pack(anchor="w", pady=(6, 0))

    def update_intelligence(self, intelligence):
        """Accept a new observation and refresh the tab.

        The catalog model is built on a **worker thread**, because a large
        Pyanodons catalog takes long enough to build that doing it on the
        Tkinter main thread would freeze the dashboard. The result is applied
        back on the main thread, so no Tk widget is ever touched from the
        worker.

        A frame arrives many times per second and the model only changes when
        the observed catalog changes. At most **one** model build runs at a
        time; a newer observation is stored and picked up when the running
        build finishes, so a fast frame rate cannot pile up threads.
        """
        self.intelligence = intelligence
        self.plan_button.configure(
            state="normal" if intelligence.get("planner_ready") is True else "disabled"
        )
        self.production_button.configure(
            state="normal" if intelligence.get("planner_ready") is True else "disabled"
        )
        if self._model_building:
            # A build is already running. Keep only the newest observation and
            # let the running worker pick it up.
            self._pending_intelligence = intelligence
            self._model_generation += 1
            return
        self.status.set("Building the recipe catalog view...")
        self._model_generation += 1
        generation = self._model_generation
        self._model_building = True
        worker = threading.Thread(
            target=self._build_model_worker,
            args=(intelligence, generation),
            daemon=True,
        )
        worker.start()
        self._poll_model()

    def _build_model_worker(self, intelligence, generation):
        """Build the catalog model away from the UI thread."""
        try:
            model = catalog_view_model(intelligence)
        except Exception as exc:  # noqa: BLE001 - reported, never raised at the UI
            model = {
                "status": f"Recipe catalog view unavailable: {exc}",
                "metadata": "The catalog model could not be built",
                "recipes": [],
                "research": [],
                "unresearched_technologies": {},
                "unsupported_mechanics": [],
            }
        self._model_queue.put((generation, model))

    def _poll_model(self):
        """Apply a finished catalog model on the main thread."""
        try:
            generation, model = self._model_queue.get_nowait()
        except queue.Empty:
            self.after(30, self._poll_model)
            return
        self._model_building = False
        if generation != self._model_generation:
            # Do not poll an empty queue forever. Start the newest queued
            # observation once the old worker has finished.
            pending = self._pending_intelligence
            self._pending_intelligence = None
            if pending is not None:
                self.update_intelligence(pending)
            return
        self.model = model
        self.status.set(self.model["status"])
        self.metadata.set(self.model["metadata"])
        self.populate_recipes()
        self.research_list.delete(0, "end")
        for technology in self.model["research"]:
            self.research_list.insert("end", technology)
        self.unresearched_list.delete(0, "end")
        for name in sorted(self.model["unresearched_technologies"]):
            state = self.model["unresearched_technologies"][name]
            self.unresearched_list.insert(
                "end",
                f"{name} ({'enabled' if state['enabled'] else 'disabled'})",
            )
        if self.recipe_list.selection():
            self.show_recipe()
        else:
            self.recipe_detail_text = ""
            self.update_product_targets({"products": []})
        if self.model["recipes"]:
            self.set_details("Select a recipe to inspect its observed details and outputs.")
        else:
            self.set_details(
                "Recipe metadata unavailable. An older backend, incomplete page, "
                "stale observation, or unqualified profile cannot be treated as a plan."
            )
        # A newer observation may have arrived while this build was running.
        pending = self._pending_intelligence
        self._pending_intelligence = None
        if pending is not None:
            self.update_intelligence(pending)

    def populate_recipes(self):
        selected = self.recipe_list.selection()
        selected_name = selected[0] if selected else None
        query = self.search.get().strip().casefold()
        self.recipe_list.delete(*self.recipe_list.get_children())
        matches = shown = 0
        for row in self.model["recipes"]:
            if query and query not in row["search"]:
                continue
            matches += 1
            if shown >= MAX_VISIBLE_RECIPES:
                continue  # Tk insertion is costly for large modpacks; search sees all rows.
            self.recipe_list.insert(
                "", "end", iid=row["name"],
                values=(
                    row["availability"], row["category"], row["products"],
                    row["unlock_summary"],
                ),
                text=row["name"],
            )
            shown += 1
        self.status.set(
            self.model["status"] + (
                f" | Showing {shown}/{matches} matches; refine the recipe search"
                if matches > shown else ""
            )
        )
        if selected_name and self.recipe_list.exists(selected_name):
            self.recipe_list.selection_set(selected_name)
            self.recipe_list.see(selected_name)
        else:
            self.recipe_detail_text = ""
            self.update_product_targets({"products": []})
            if self.model["recipes"]:
                self.set_details(
                    "Select a recipe to inspect its observed details and outputs."
                )

    def show_recipe(self, _event=None):
        selection = self.recipe_list.selection()
        if not selection:
            return
        row = next(
            (item for item in self.model["recipes"] if item["name"] == selection[0]),
            None,
        )
        if row is None:
            return
        recipe = row["recipe"]
        self.update_product_targets(recipe)
        unlocks = recipe.get("unlock_technologies")
        if unlocks is None:
            unlock_details = "Technology unlock effects: not reported by this backend"
        elif unlocks:
            unlock_details = "Technology unlock effects:\n" + "\n".join(
                f"- {unlock['name']}: "
                + (
                    "researched"
                    if unlock["researched"]
                    else "not researched; technology enabled"
                    if unlock["enabled"]
                    else "not researched; technology disabled"
                )
                for unlock in unlocks
            )
            if any(not item["researched"] and item["enabled"] for item in unlocks):
                unlock_details += (
                    "\n  Research prerequisites/availability are not verified here."
                )
        else:
            unlock_details = (
                "No recipe-unlock effect was observed; the reason this recipe is "
                "disabled is unknown."
            )
        categories = row["categories"]
        category_line = (
            f"Category: {row['category']}"
            + (f" (also {', '.join(categories[1:])})" if len(categories) > 1 else "")
        )
        yield_lines = []
        for part in recipe["products"]:
            entry = yield_of_part(part)
            detail = _format_part(part)
            if entry.is_uncertain:
                bounds = []
                if entry.minimum is not None:
                    bounds.append(f"min {entry.minimum:g}")
                if entry.maximum is not None:
                    bounds.append(f"max {entry.maximum:g}")
                if entry.expected is not None:
                    bounds.append(f"expected {entry.expected:g}")
                elif entry.expected is None and entry.deterministic is False:
                    bounds.append("expected unknown")
                if entry.probability is not None:
                    bounds.append(f"probability {entry.probability:g}")
                yield_lines.append(
                    f"  {part['type']}:{part['name']} — {detail}"
                    + (f" ({', '.join(bounds)})" if bounds else "")
                )
                for reason in entry.reasons:
                    yield_lines.append(f"    - {reason}")
        yield_block = ""
        if yield_lines:
            yield_block = "Output yield:\n" + "\n".join(yield_lines) + "\n"
        feasibility_line = f"Feasibility: {row['feasibility_status']}"
        if row["blocked_by"]:
            feasibility_line += " (blocked by " + ", ".join(row["blocked_by"]) + ")"
        self.recipe_detail_text = (
            f"{row['name']}\n"
            f"Availability: {row['availability']}\n"
            f"{feasibility_line}\n"
            f"{category_line}\n"
            f"Crafting time: {row['crafting_time']:g} s\n"
            f"Ingredients: {row['ingredients']}\n"
            f"Products: {row['products']}\n"
            f"{yield_block}"
            f"{unlock_details}\n"
            f"Recipe shape: {'simple item recipe' if recipe['simple'] else 'complex/unsupported'}\n"
            "Rates, machine compatibility, and production feasibility are not inferred here."
        )
        self.set_details(self.recipe_detail_text)

    def update_product_targets(self, recipe):
        choices = {}
        for product in recipe["products"]:
            label = f"{product['type']}: {product['name']}"
            choices[label] = (product["type"], product["name"])
        self.product_choices = choices
        labels = list(choices)
        self.product_selector.configure(values=labels)
        if self.product_target.get() not in choices:
            self.product_target.set(labels[0] if labels else "")

    def show_material_plan(self):
        target = self.product_choices.get(self.product_target.get())
        if target is None:
            self.set_details("Select an observed recipe output to preview its material requirements.")
            return
        try:
            plan = plan_product_materials(
                self.intelligence,
                target[0],
                target[1],
                float(self.target_amount.get()),
            )
        except ValueError as exc:
            self.set_details(
                self.recipe_detail_text + f"\n\nMaterial planning unavailable: {exc}"
            )
            return
        self.set_details(self.recipe_detail_text + "\n\n" + format_material_plan(plan))

    def _optional_number(self, raw):
        """Return the entered number, or None when the field is empty.

        An empty machine field means the value was **not** established, so it
        is passed as None and the plan reports it as unsupported. A field that
        holds something that is not a number is a user error and is reported.
        """
        text = (raw or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise ValueError(f"'{text}' is not a number") from exc

    def show_production_plan(self):
        """Show the production plan for the selected output at the wanted rate."""
        target = self.product_choices.get(self.product_target.get())
        if target is None:
            self.set_details(
                "Select an observed recipe output to plan its production."
            )
            return
        try:
            rate = float((self.target_rate.get() or "").strip())
        except ValueError:
            self.set_details("The target rate must be a number.")
            return
        if rate <= 0:
            self.set_details("The target rate must be greater than zero.")
            return
        try:
            machine_speed = self._optional_number(self.machine_speed.get())
            machine_power_kw = self._optional_number(self.machine_power_kw.get())
        except ValueError as exc:
            self.set_details(self.recipe_detail_text + f"\n\nProduction plan: {exc}")
            return

        unit = self.rate_unit.get()
        try:
            plan = plan_target_production(
                self.intelligence,
                target[0],
                target[1],
                per_second=rate if unit == "per_second" else None,
                per_minute=rate if unit == "per_minute" else None,
                machine_speed=machine_speed,
                machine_energy_kw=machine_power_kw,
            )
        except ValueError as exc:
            self.set_details(
                self.recipe_detail_text + f"\n\nProduction planning unavailable: {exc}"
            )
            return
        self.set_details(
            self.recipe_detail_text + "\n\n" + format_target_production(plan)
        )

    def set_details(self, value):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")
