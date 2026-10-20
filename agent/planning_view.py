"""Read-only recipe and research catalog browser."""

import tkinter as tk
from tkinter import scrolledtext, ttk

from recipe_material_planner import format_material_plan, plan_product_materials


def catalog_view_model(intelligence):
    capabilities = intelligence.get("capabilities")
    catalog_status = intelligence.get("catalog_status") or {}
    if not isinstance(capabilities, dict):
        return {
            "status": intelligence.get("reason", "Recipe/research catalog unavailable"),
            "metadata": "No same-tick capability snapshot",
            "recipes": [],
            "research": [],
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
            f"{part['amount']:g} {part['type']}:{part['name']}"
            for part in recipe["products"]
        )
        ingredients = ", ".join(
            f"{part['amount']:g} {part['type']}:{part['name']}"
            for part in recipe["ingredients"]
        ) or "(no ingredients reported)"
        availability = (
            "Hidden" if recipe["hidden"]
            else "Enabled" if recipe["enabled"]
            else "Disabled"
        )
        recipes.append({
            "name": recipe["name"],
            "availability": availability,
            "category": recipe["category"],
            "crafting_time": recipe["crafting_time"],
            "ingredients": ingredients,
            "products": products,
            "unlock_summary": unlock_summary,
            "search": " ".join([
                recipe["name"], recipe["category"], ingredients, products, availability,
                *(unlock["name"] for unlock in unlocks), unlock_summary,
            ]).casefold(),
            "recipe": recipe,
        })

    research = capabilities.get("research", [])
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
        f"Enabled content: {enabled_content_label}\n"
        f"Source change fingerprint: {source_fingerprint} (not authentication)\n"
        f"{coverage_note}"
    )
    return {
        "status": ready_note,
        "metadata": metadata,
        "recipes": recipes,
        "research": research,
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
        self.intelligence = intelligence
        self.model = catalog_view_model(intelligence)
        self.status.set(self.model["status"])
        self.metadata.set(self.model["metadata"])
        self.plan_button.configure(
            state="normal" if intelligence.get("planner_ready") is True else "disabled"
        )
        self.populate_recipes()
        self.research_list.delete(0, "end")
        for technology in self.model["research"]:
            self.research_list.insert("end", technology)
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

    def populate_recipes(self):
        selected = self.recipe_list.selection()
        selected_name = selected[0] if selected else None
        query = self.search.get().strip().casefold()
        self.recipe_list.delete(*self.recipe_list.get_children())
        for row in self.model["recipes"]:
            if query and query not in row["search"]:
                continue
            self.recipe_list.insert(
                "", "end", iid=row["name"],
                values=(
                    row["availability"], row["category"], row["products"],
                    row["unlock_summary"],
                ),
                text=row["name"],
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
        self.recipe_detail_text = (
            f"{row['name']}\n"
            f"Availability: {row['availability']}\n"
            f"Category: {row['category']}\n"
            f"Crafting time: {row['crafting_time']:g} s\n"
            f"Ingredients: {row['ingredients']}\n"
            f"Products: {row['products']}\n"
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

    def set_details(self, value):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")
