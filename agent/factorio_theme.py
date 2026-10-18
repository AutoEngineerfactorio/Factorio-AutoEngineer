"""Original industrial desktop styling; no game textures are bundled."""

from tkinter import ttk

BG = "#20221f"
PANEL = "#333630"
INSET = "#252822"
TEXT = "#e2e1d5"
MUTED = "#a8ae9d"
AMBER = "#e8b45b"


def apply_theme(root):
    root.configure(background=BG)
    root.option_add("*Font", ("Segoe UI", 10))
    root.option_add("*TCombobox*Listbox.background", INSET)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#6e5935")
    root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(
        ".",
        background=PANEL,
        foreground=TEXT,
        font=("Segoe UI", 10),
        bordercolor="#151813",
        lightcolor="#52574b",
        darkcolor="#171b15",
    )
    s.configure("TFrame", background=BG)
    s.configure("Panel.TFrame", background=PANEL, relief="raised", borderwidth=2)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Heading.TLabel", foreground=AMBER, font=("Bahnschrift", 20, "bold"))
    s.configure("Section.TLabel", foreground=AMBER, font=("Segoe UI", 10, "bold"))
    s.configure("Value.TLabel", foreground=TEXT, font=("Consolas", 11, "bold"))
    s.configure("Ready.TLabel", foreground="#a6c67e")
    s.configure("Error.TLabel", foreground="#ee9b80")
    s.configure(
        "Badge.TLabel",
        background="#574930",
        foreground="#f1ca83",
        padding=(10, 5),
        font=("Segoe UI", 9, "bold"),
    )
    s.configure("TLabelframe", background=BG, relief="sunken", borderwidth=2)
    s.configure("TLabelframe.Label", background=BG, foreground=AMBER, font=("Segoe UI", 9, "bold"))
    s.configure(
        "TButton",
        background="#4b5145",
        foreground=TEXT,
        relief="raised",
        borderwidth=2,
        padding=(12, 8),
        font=("Segoe UI", 10, "bold"),
        focusthickness=1,
        focuscolor=AMBER,
    )
    s.map(
        "TButton",
        background=[("disabled", "#33382f"), ("pressed", "#30362a"), ("active", "#606a52")],
        foreground=[("disabled", "#838a78")],
    )
    for name, bg, fg, hover in [
        ("Accent", "#be8b37", "#14180f", "#e8b45b"),
        ("Approve", "#567944", "#f4f4e7", "#6e9854"),
        ("Danger", "#8a3e2d", "#fff0df", "#b84b32"),
    ]:
        s.configure(name + ".TButton", background=bg, foreground=fg)
        s.map(
            name + ".TButton",
            background=[("disabled", "#33382f"), ("pressed", bg), ("active", hover)],
            foreground=[("disabled", "#838a78")],
        )
    s.configure(
        "TEntry",
        fieldbackground=INSET,
        foreground=TEXT,
        insertcolor=AMBER,
        padding=7,
        borderwidth=2,
    )
    s.configure(
        "TCombobox",
        fieldbackground=INSET,
        background="#4b5145",
        foreground=TEXT,
        arrowcolor=AMBER,
        padding=5,
    )
    s.map(
        "TCombobox",
        fieldbackground=[("readonly", INSET)],
        foreground=[("readonly", TEXT), ("disabled", "#838a78")],
        selectbackground=[("readonly", INSET)],
        selectforeground=[("readonly", TEXT)],
    )
    s.configure("TSpinbox", fieldbackground=INSET, foreground=TEXT, arrowcolor=AMBER, padding=5)
    s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    s.configure(
        "TNotebook.Tab",
        background="#353b2f",
        foreground=MUTED,
        padding=(18, 9),
        font=("Segoe UI", 10, "bold"),
    )
    s.map(
        "TNotebook.Tab",
        background=[("selected", "#5b5036"), ("active", "#49513e")],
        foreground=[("selected", "#f3d08c"), ("active", TEXT)],
    )
    s.configure("Horizontal.TPanedwindow", background=BG, sashwidth=7)
    s.configure(
        "Vertical.TScrollbar",
        background="#505747",
        troughcolor=INSET,
        arrowcolor=AMBER,
        borderwidth=1,
    )
    s.configure("TSeparator", background="#65694f")
    return s
