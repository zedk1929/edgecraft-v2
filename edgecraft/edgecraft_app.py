"""Native desktop interface for the Edgecraft Quant Research Workbench."""

from __future__ import annotations

import math
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
import pandas as pd

from quant_engine import (
    STRATEGIES,
    BacktestResult,
    generate_demo_data,
    load_price_csv,
    parameter_sweep,
    run_backtest,
)


COLORS = {
    "bg": "#09100f",
    "panel": "#111c1a",
    "panel_2": "#16231f",
    "line": "#263a34",
    "text": "#edf7f2",
    "muted": "#8ca198",
    "faint": "#5f756d",
    "accent": "#b9ff66",
    "teal": "#69e6c3",
    "red": "#ff7b76",
    "amber": "#f7c768",
}


def format_percent(value: float) -> str:
    return f"{value * 100:+.1f}%"


def format_money(value: float) -> str:
    return f"${value:,.0f}"


class LineChart(tk.Canvas):
    """A lightweight, dependency-free time-series chart for Tk."""

    def __init__(self, parent: tk.Widget, title: str, height: int = 220) -> None:
        super().__init__(parent, height=height, bg=COLORS["panel"], highlightthickness=0)
        self.title = title
        self.series: list[tuple[str, np.ndarray, str]] = []
        self.dates: list[pd.Timestamp] = []
        self.split_index: int | None = None
        self.percent_axis = False
        self.bind("<Configure>", lambda _event: self.draw())

    def set_data(
        self,
        dates: pd.Series,
        series: list[tuple[str, pd.Series | np.ndarray, str]],
        split_index: int | None = None,
        percent_axis: bool = False,
    ) -> None:
        self.dates = list(pd.to_datetime(dates))
        self.series = [(name, np.asarray(values, dtype=float), color) for name, values, color in series]
        self.split_index = split_index
        self.percent_axis = percent_axis
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 120 or height < 100:
            return
        left, right, top, bottom = 70, 18, 36, 28
        plot_width, plot_height = width - left - right, height - top - bottom
        self.create_text(left, 16, text=self.title, fill=COLORS["text"], anchor="w", font=("Segoe UI", 10, "bold"))
        if not self.series or not self.dates:
            self.create_text(width / 2, height / 2, text="Run a backtest to populate this chart", fill=COLORS["muted"])
            return

        finite_values = np.concatenate([values[np.isfinite(values)] for _, values, _ in self.series])
        if not len(finite_values):
            return
        y_min, y_max = float(finite_values.min()), float(finite_values.max())
        padding = max((y_max - y_min) * 0.08, abs(y_max) * 0.02, 0.01)
        y_min -= padding
        y_max += padding
        count = max(len(self.dates) - 1, 1)

        def x(index: int) -> float:
            return left + index / count * plot_width

        def y(value: float) -> float:
            return top + (y_max - value) / max(y_max - y_min, 1e-9) * plot_height

        for step in range(5):
            value = y_min + (y_max - y_min) * step / 4
            y_pos = y(value)
            self.create_line(left, y_pos, width - right, y_pos, fill=COLORS["line"])
            label = f"{value:.1f}%" if self.percent_axis else (f"${value:,.0f}" if abs(value) >= 100 else f"{value:,.1f}")
            self.create_text(left - 8, y_pos, text=label, fill=COLORS["faint"], anchor="e", font=("Consolas", 8))

        if self.split_index is not None and 0 < self.split_index < len(self.dates):
            split_x = x(self.split_index)
            self.create_line(split_x, top, split_x, height - bottom, fill=COLORS["amber"], dash=(4, 4))
            self.create_text(split_x + 5, top + 8, text="OUT-OF-SAMPLE", fill=COLORS["amber"], anchor="nw", font=("Segoe UI", 7, "bold"))

        max_points = max(80, int(plot_width))
        step = max(1, math.ceil(len(self.dates) / max_points))
        for name, values, color in self.series:
            indices = list(range(0, len(values), step))
            if indices[-1] != len(values) - 1:
                indices.append(len(values) - 1)
            points: list[float] = []
            for index in indices:
                if np.isfinite(values[index]):
                    points.extend((x(index), y(values[index])))
            if len(points) >= 4:
                self.create_line(*points, fill=color, width=2, smooth=False)

        legend_x = width - right
        for name, _values, color in reversed(self.series):
            text_id = self.create_text(legend_x, 16, text=name, fill=COLORS["muted"], anchor="e", font=("Segoe UI", 8))
            box = self.bbox(text_id)
            if box:
                self.create_oval(box[0] - 13, 12, box[0] - 5, 20, fill=color, outline="")
                legend_x = box[0] - 22

        first_date, last_date = self.dates[0], self.dates[-1]
        self.create_text(left, height - 9, text=first_date.strftime("%b %Y"), fill=COLORS["faint"], anchor="w", font=("Segoe UI", 8))
        self.create_text(width - right, height - 9, text=last_date.strftime("%b %Y"), fill=COLORS["faint"], anchor="e", font=("Segoe UI", 8))


class MetricCard(tk.Frame):
    def __init__(self, parent: tk.Widget, label: str) -> None:
        super().__init__(parent, bg=COLORS["panel_2"], padx=16, pady=12, highlightbackground=COLORS["line"], highlightthickness=1)
        self.value = tk.StringVar(value="—")
        tk.Label(self, text=label.upper(), bg=COLORS["panel_2"], fg=COLORS["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(self, textvariable=self.value, bg=COLORS["panel_2"], fg=COLORS["text"], font=("Segoe UI Semibold", 18)).pack(anchor="w", pady=(5, 0))


class EdgecraftApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Edgecraft — Quant Research Workbench")
        self.geometry("1380x900")
        self.minsize(1080, 720)
        self.configure(bg=COLORS["bg"])
        self.data = generate_demo_data()
        self.dataset_name = "Synthetic regime demo"
        self.result: BacktestResult | None = None
        self.sweep: pd.DataFrame | None = None
        self._configure_styles()
        self._build_ui()
        self.after(100, self.run_research)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 9))
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("Section.TLabel", background=COLORS["panel"], foreground=COLORS["muted"], font=("Segoe UI", 8, "bold"))
        style.configure("TButton", background=COLORS["panel_2"], foreground=COLORS["text"], bordercolor=COLORS["line"], padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", COLORS["line"])])
        style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["bg"], bordercolor=COLORS["accent"], padding=(14, 9))
        style.map("Accent.TButton", background=[("active", "#9eea48")])
        style.configure("TEntry", fieldbackground=COLORS["bg"], foreground=COLORS["text"], bordercolor=COLORS["line"], insertcolor=COLORS["text"], padding=7)
        style.configure("TCombobox", fieldbackground=COLORS["bg"], background=COLORS["panel_2"], foreground=COLORS["text"], arrowcolor=COLORS["accent"], bordercolor=COLORS["line"], padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["bg"])], foreground=[("readonly", COLORS["text"])])
        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["bg"], foreground=COLORS["muted"], padding=(14, 8), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", COLORS["panel"])], foreground=[("selected", COLORS["accent"])])
        style.configure("Treeview", background=COLORS["panel"], fieldbackground=COLORS["panel"], foreground=COLORS["text"], rowheight=27, bordercolor=COLORS["line"], font=("Consolas", 9))
        style.configure("Treeview.Heading", background=COLORS["panel_2"], foreground=COLORS["muted"], relief="flat", font=("Segoe UI", 8, "bold"))
        style.map("Treeview", background=[("selected", COLORS["line"])], foreground=[("selected", COLORS["accent"])])
        style.configure("Horizontal.TScale", background=COLORS["panel"], troughcolor=COLORS["bg"])

    def _build_ui(self) -> None:
        self._build_header()
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self._build_sidebar(body)
        self._build_workspace(body)
        self.status = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status, bg=COLORS["bg"], fg=COLORS["faint"], anchor="w", padx=20, pady=7, font=("Segoe UI", 8)).pack(fill="x", side="bottom")

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["bg"], padx=20, pady=15)
        header.pack(fill="x")
        mark = tk.Label(header, text="E", width=2, bg=COLORS["accent"], fg=COLORS["bg"], font=("Segoe UI Black", 14))
        mark.pack(side="left")
        title = tk.Frame(header, bg=COLORS["bg"])
        title.pack(side="left", padx=11)
        tk.Label(title, text="EDGECRAFT", bg=COLORS["bg"], fg=COLORS["text"], font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(title, text="QUANT RESEARCH WORKBENCH", bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 7, "bold")).pack(anchor="w")
        self.dataset_label = tk.StringVar(value=self.dataset_name)
        tk.Label(header, textvariable=self.dataset_label, bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack(side="left", padx=28)
        ttk.Button(header, text="Export results", command=self.export_results).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Load CSV", command=self.load_csv).pack(side="right", padx=(8, 0))
        ttk.Button(header, text="Demo data", command=self.load_demo).pack(side="right")

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = ttk.Frame(parent, style="Panel.TFrame", width=292, padding=20)
        sidebar.pack(side="left", fill="y", padx=(0, 14))
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="RESEARCH DESIGN", style="Section.TLabel").pack(anchor="w", pady=(0, 12))

        self.strategy_var = tk.StringVar(value="Moving Average Crossover")
        ttk.Label(sidebar, text="Strategy", style="Section.TLabel").pack(anchor="w", pady=(4, 5))
        strategy_box = ttk.Combobox(sidebar, textvariable=self.strategy_var, values=list(STRATEGIES), state="readonly")
        strategy_box.pack(fill="x")
        strategy_box.bind("<<ComboboxSelected>>", self.on_strategy_change)

        self.param_labels: list[ttk.Label] = []
        self.param_vars = [tk.StringVar() for _ in range(3)]
        self.param_entries: list[ttk.Entry] = []
        for index in range(3):
            label = ttk.Label(sidebar, text="Parameter", style="Section.TLabel")
            label.pack(anchor="w", pady=(14, 5))
            entry = ttk.Entry(sidebar, textvariable=self.param_vars[index])
            entry.pack(fill="x")
            self.param_labels.append(label)
            self.param_entries.append(entry)

        ttk.Separator(sidebar).pack(fill="x", pady=19)
        self.cash_var = tk.StringVar(value="10000")
        self.fee_var = tk.StringVar(value="5")
        self._field(sidebar, "Starting capital", self.cash_var)
        self._field(sidebar, "Trading cost (bps per side)", self.fee_var)

        self.split_var = tk.DoubleVar(value=70)
        self.split_label = ttk.Label(sidebar, text="TRAINING WINDOW · 70%", style="Section.TLabel")
        self.split_label.pack(anchor="w", pady=(14, 4))
        split = ttk.Scale(sidebar, from_=50, to=90, variable=self.split_var, command=self.on_split_change)
        split.pack(fill="x")

        ttk.Button(sidebar, text="Run backtest", style="Accent.TButton", command=self.run_research).pack(fill="x", pady=(23, 8))
        ttk.Button(sidebar, text="Sweep parameters", command=self.run_sweep).pack(fill="x")

        note = "Signals execute one bar later. Costs are charged when exposure changes. The amber divider marks unseen test data."
        tk.Label(sidebar, text=note, wraplength=246, justify="left", bg=COLORS["panel"], fg=COLORS["faint"], font=("Segoe UI", 8)).pack(side="bottom", fill="x", pady=(18, 0))
        self._set_parameter_fields(reset=True)

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label.upper(), style="Section.TLabel").pack(anchor="w", pady=(13, 5))
        ttk.Entry(parent, textvariable=variable).pack(fill="x")

    def _build_workspace(self, parent: ttk.Frame) -> None:
        workspace = ttk.Frame(parent)
        workspace.pack(side="left", fill="both", expand=True)
        metric_row = tk.Frame(workspace, bg=COLORS["bg"])
        metric_row.pack(fill="x", pady=(0, 12))
        metric_names = ("Total return", "CAGR", "Sharpe", "Max drawdown", "Test Sharpe", "Trades")
        self.metrics: dict[str, MetricCard] = {}
        for index, name in enumerate(metric_names):
            metric_row.grid_columnconfigure(index, weight=1)
            card = MetricCard(metric_row, name)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 4, 0 if index == len(metric_names) - 1 else 4))
            self.metrics[name] = card

        self.notebook = ttk.Notebook(workspace)
        self.notebook.pack(fill="both", expand=True)
        overview = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.trade_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.sweep_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.data_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.notebook.add(overview, text="Overview")
        self.notebook.add(self.trade_tab, text="Trades")
        self.notebook.add(self.sweep_tab, text="Parameter sweep")
        self.notebook.add(self.data_tab, text="Data")

        overview.grid_rowconfigure(0, weight=1)
        overview.grid_rowconfigure(1, weight=1)
        overview.grid_rowconfigure(2, weight=1)
        overview.grid_columnconfigure(0, weight=1)
        self.price_chart = LineChart(overview, "PRICE & RESEARCH SPLIT")
        self.price_chart.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        self.equity_chart = LineChart(overview, "EQUITY CURVE")
        self.equity_chart.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self.drawdown_chart = LineChart(overview, "DRAWDOWN", height=150)
        self.drawdown_chart.grid(row=2, column=0, sticky="nsew")

        self.trade_tree = self._make_tree(self.trade_tab, ("trade", "entry", "exit", "entry_price", "exit_price", "return", "bars"))
        self.sweep_tree = self._make_tree(self.sweep_tab, ("rank", "parameters", "train_sharpe", "test_sharpe", "test_return", "max_dd", "trades"))
        self.sweep_tree.bind("<Double-1>", self.apply_sweep_row)
        self.data_tree = self._make_tree(self.data_tab, ("date", "open", "high", "low", "close", "volume"))

    def _make_tree(self, parent: ttk.Frame, columns: tuple[str, ...]) -> ttk.Treeview:
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        scroll_y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scroll_x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        for column in columns:
            tree.heading(column, text=column.replace("_", " ").upper())
            tree.column(column, width=120, anchor="e" if column not in ("entry", "exit", "date", "parameters") else "w")
        return tree

    def _set_parameter_fields(self, reset: bool) -> None:
        spec = STRATEGIES[self.strategy_var.get()]
        for index, (label, default) in enumerate(zip(spec["labels"], spec["defaults"])):
            self.param_labels[index].configure(text=label.upper())
            disabled = label == "Unused"
            self.param_entries[index].configure(state="disabled" if disabled else "normal")
            if reset:
                self.param_vars[index].set(str(default))

    def on_strategy_change(self, _event: object = None) -> None:
        self._set_parameter_fields(reset=True)
        self.status.set(f"Strategy changed to {self.strategy_var.get()}. Run the backtest to refresh results.")

    def on_split_change(self, value: str) -> None:
        self.split_label.configure(text=f"TRAINING WINDOW · {float(value):.0f}%")

    def _parameters(self) -> dict[str, float]:
        values = [float(variable.get()) for variable in self.param_vars]
        strategy = self.strategy_var.get()
        if strategy == "Moving Average Crossover":
            return {"fast": int(values[0]), "slow": int(values[1])}
        if strategy == "RSI Mean Reversion":
            return {"period": int(values[0]), "entry": values[1], "exit": values[2]}
        return {"entry_window": int(values[0]), "exit_window": int(values[1])}

    def run_research(self) -> None:
        try:
            self.status.set("Running backtest…")
            self.update_idletasks()
            self.result = run_backtest(
                self.data,
                self.strategy_var.get(),
                self._parameters(),
                float(self.cash_var.get()),
                float(self.fee_var.get()),
                self.split_var.get() / 100,
            )
            self._render_result()
            self.status.set(f"Complete · {len(self.data):,} rows · {self.result.strategy} · signals lagged one bar")
        except Exception as error:
            self.status.set("Backtest failed")
            messagebox.showerror("Backtest error", str(error), parent=self)

    def _render_result(self) -> None:
        assert self.result is not None
        metrics = self.result.metrics
        values = {
            "Total return": format_percent(metrics["total_return"]),
            "CAGR": format_percent(metrics["cagr"]),
            "Sharpe": f"{metrics['sharpe']:.2f}",
            "Max drawdown": format_percent(metrics["max_drawdown"]),
            "Test Sharpe": f"{self.result.test_metrics['sharpe']:.2f}",
            "Trades": f"{metrics['trades']:.0f}",
        }
        for name, value in values.items():
            self.metrics[name].value.set(value)

        frame = self.result.frame
        split_index = int((frame["segment"] == "Train").sum())
        self.price_chart.set_data(frame["date"], [("Close", frame["close"], COLORS["teal"])], split_index)
        self.equity_chart.set_data(frame["date"], [
            ("Strategy", frame["equity"], COLORS["accent"]),
            ("Buy & hold", frame["benchmark"], COLORS["muted"]),
        ], split_index)
        self.drawdown_chart.set_data(frame["date"], [("Strategy DD", frame["drawdown"] * 100, COLORS["red"])], split_index, percent_axis=True)
        self._render_trade_log()
        self._render_data()

    def _clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _render_trade_log(self) -> None:
        self._clear_tree(self.trade_tree)
        if self.result is None:
            return
        for _, trade in self.result.trade_log.iterrows():
            self.trade_tree.insert("", "end", values=(
                int(trade["trade"]),
                pd.Timestamp(trade["entry_date"]).strftime("%Y-%m-%d"),
                pd.Timestamp(trade["exit_date"]).strftime("%Y-%m-%d"),
                f"${trade['entry_price']:,.2f}",
                f"${trade['exit_price']:,.2f}",
                format_percent(trade["return"]),
                int(trade["bars"]),
            ))

    def _render_data(self) -> None:
        self._clear_tree(self.data_tree)
        for _, row in self.data.tail(500).iloc[::-1].iterrows():
            values = [pd.Timestamp(row["date"]).strftime("%Y-%m-%d")]
            for column in ("open", "high", "low", "close"):
                values.append(f"{row[column]:,.2f}" if column in row and pd.notna(row[column]) else "—")
            values.append(f"{row['volume']:,.0f}" if "volume" in row and pd.notna(row["volume"]) else "—")
            self.data_tree.insert("", "end", values=values)

    def run_sweep(self) -> None:
        try:
            self.status.set("Testing parameter grid…")
            self.update_idletasks()
            self.sweep = parameter_sweep(
                self.data,
                self.strategy_var.get(),
                float(self.cash_var.get()),
                float(self.fee_var.get()),
                self.split_var.get() / 100,
            )
            self._clear_tree(self.sweep_tree)
            parameter_columns = [column for column in self.sweep.columns if column not in {"train_sharpe", "test_sharpe", "test_return", "max_drawdown", "trades"}]
            for index, row in self.sweep.iterrows():
                parameter_text = ", ".join(f"{name}={row[name]:g}" for name in parameter_columns)
                self.sweep_tree.insert("", "end", iid=str(index), values=(
                    index + 1,
                    parameter_text,
                    f"{row['train_sharpe']:.2f}",
                    f"{row['test_sharpe']:.2f}",
                    format_percent(row["test_return"]),
                    format_percent(row["max_drawdown"]),
                    f"{row['trades']:.0f}",
                ))
            self.notebook.select(self.sweep_tab)
            self.status.set("Parameter sweep complete · ranked on training Sharpe · test results remain held out")
        except Exception as error:
            self.status.set("Parameter sweep failed")
            messagebox.showerror("Sweep error", str(error), parent=self)

    def apply_sweep_row(self, _event: object = None) -> None:
        if self.sweep is None:
            return
        selection = self.sweep_tree.selection()
        if not selection:
            return
        row = self.sweep.iloc[int(selection[0])]
        strategy = self.strategy_var.get()
        if strategy == "Moving Average Crossover":
            values = (row["fast"], row["slow"], 0)
        elif strategy == "RSI Mean Reversion":
            values = (row["period"], row["entry"], row["exit"])
        else:
            values = (row["entry_window"], row["exit_window"], 0)
        for variable, value in zip(self.param_vars, values):
            variable.set(f"{value:g}")
        self.notebook.select(0)
        self.run_research()

    def load_csv(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Load price history", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.data = load_price_csv(path)
            self.dataset_name = Path(path).name
            self.dataset_label.set(f"{self.dataset_name} · {len(self.data):,} rows")
            self.run_research()
        except Exception as error:
            messagebox.showerror("Could not load CSV", str(error), parent=self)

    def load_demo(self) -> None:
        self.data = generate_demo_data()
        self.dataset_name = "Synthetic regime demo"
        self.dataset_label.set(f"{self.dataset_name} · {len(self.data):,} rows")
        self.run_research()

    def export_results(self) -> None:
        if self.result is None:
            messagebox.showinfo("Nothing to export", "Run a backtest first.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="Export backtest results", defaultextension=".csv", initialfile="edgecraft_backtest.csv", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        self.result.frame.to_csv(path, index=False)
        self.status.set(f"Exported {len(self.result.frame):,} rows to {Path(path).name}")


if __name__ == "__main__":
    EdgecraftApp().mainloop()
