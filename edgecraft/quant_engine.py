"""Research and backtesting engine for Edgecraft.

The module has no UI dependencies, so strategies and metrics can be tested,
reused in notebooks, or driven by the native desktop application.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass(frozen=True)
class BacktestResult:
    frame: pd.DataFrame
    metrics: dict[str, float]
    train_metrics: dict[str, float]
    test_metrics: dict[str, float]
    trade_log: pd.DataFrame
    strategy: str
    parameters: dict[str, float]


STRATEGIES: dict[str, dict[str, Any]] = {
    "Moving Average Crossover": {
        "labels": ("Fast window", "Slow window", "Unused"),
        "defaults": (20, 100, 0),
        "limits": ((2, 200), (5, 400), (0, 0)),
    },
    "RSI Mean Reversion": {
        "labels": ("RSI period", "Entry below", "Exit above"),
        "defaults": (14, 30, 55),
        "limits": ((2, 100), (5, 50), (50, 95)),
    },
    "Price Breakout": {
        "labels": ("Entry lookback", "Exit lookback", "Unused"),
        "defaults": (55, 20, 0),
        "limits": ((2, 300), (2, 200), (0, 0)),
    },
}


def generate_demo_data(rows: int = 1_260, seed: int = 21) -> pd.DataFrame:
    """Generate five years of regime-changing daily OHLCV data."""
    if rows < 100:
        raise ValueError("Demo data requires at least 100 rows.")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=rows)
    thirds = rows // 3
    drift = np.r_[
        np.full(thirds, 0.00055),
        np.full(thirds, -0.00012),
        np.full(rows - 2 * thirds, 0.00075),
    ]
    volatility = np.r_[
        np.full(thirds, 0.010),
        np.full(thirds, 0.018),
        np.full(rows - 2 * thirds, 0.012),
    ]
    shocks = rng.normal(drift, volatility)
    close = 100 * np.exp(np.cumsum(shocks))
    overnight = rng.normal(0, 0.0025, rows)
    open_price = np.r_[close[0], close[:-1]] * (1 + overnight)
    spread = np.abs(rng.normal(0.006, 0.003, rows))
    high = np.maximum(open_price, close) * (1 + spread)
    low = np.minimum(open_price, close) * (1 - spread)
    volume = rng.lognormal(mean=14.0, sigma=0.35, size=rows).astype(int)
    return pd.DataFrame({
        "date": dates,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def load_price_csv(path: str | Path) -> pd.DataFrame:
    """Load and normalize a CSV with a date column and a close/price column."""
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError("The selected CSV is empty.")

    normalized = {str(column).strip().lower().replace("_", " "): column for column in frame.columns}
    date_candidates = ("date", "datetime", "timestamp", "time")
    price_candidates = ("adj close", "adjusted close", "close", "price", "last")
    date_source = next((normalized[name] for name in date_candidates if name in normalized), None)
    close_source = next((normalized[name] for name in price_candidates if name in normalized), None)
    if date_source is None or close_source is None:
        raise ValueError("CSV needs a Date/Datetime column and a Close/Adj Close/Price column.")

    result = pd.DataFrame({
        "date": pd.to_datetime(frame[date_source], errors="coerce", utc=True).dt.tz_localize(None),
        "close": pd.to_numeric(frame[close_source], errors="coerce"),
    })
    for canonical in ("open", "high", "low", "volume"):
        if canonical in normalized:
            result[canonical] = pd.to_numeric(frame[normalized[canonical]], errors="coerce")

    result = result.dropna(subset=["date", "close"])
    result = result[result["close"] > 0].sort_values("date").drop_duplicates("date", keep="last")
    if len(result) < 60:
        raise ValueError("At least 60 valid price rows are required for research.")
    return result.reset_index(drop=True)


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + relative_strength)).fillna(50)


def strategy_signal(frame: pd.DataFrame, strategy: str, parameters: dict[str, float]) -> pd.Series:
    """Return a desired long/flat position. Execution is lagged in run_backtest."""
    close = frame["close"].astype(float)
    if strategy == "Moving Average Crossover":
        fast = int(parameters["fast"])
        slow = int(parameters["slow"])
        if not 1 < fast < slow:
            raise ValueError("Fast window must be smaller than the slow window.")
        fast_ma = close.rolling(fast, min_periods=fast).mean()
        slow_ma = close.rolling(slow, min_periods=slow).mean()
        return (fast_ma > slow_ma).astype(float)

    if strategy == "RSI Mean Reversion":
        period = int(parameters["period"])
        entry = float(parameters["entry"])
        exit_level = float(parameters["exit"])
        if not 1 < period or not 0 < entry < exit_level < 100:
            raise ValueError("RSI settings must satisfy 0 < entry < exit < 100.")
        rsi = _rsi(close, period)
        values = np.zeros(len(frame), dtype=float)
        invested = False
        for index, value in enumerate(rsi.to_numpy()):
            if not invested and value < entry:
                invested = True
            elif invested and value > exit_level:
                invested = False
            values[index] = float(invested)
        return pd.Series(values, index=frame.index)

    if strategy == "Price Breakout":
        entry_window = int(parameters["entry_window"])
        exit_window = int(parameters["exit_window"])
        if entry_window < 2 or exit_window < 2:
            raise ValueError("Breakout windows must be at least two days.")
        prior_high = close.rolling(entry_window, min_periods=entry_window).max().shift(1)
        prior_low = close.rolling(exit_window, min_periods=exit_window).min().shift(1)
        values = np.zeros(len(frame), dtype=float)
        invested = False
        for index in range(len(frame)):
            if not invested and pd.notna(prior_high.iloc[index]) and close.iloc[index] > prior_high.iloc[index]:
                invested = True
            elif invested and pd.notna(prior_low.iloc[index]) and close.iloc[index] < prior_low.iloc[index]:
                invested = False
            values[index] = float(invested)
        return pd.Series(values, index=frame.index)

    raise ValueError(f"Unknown strategy: {strategy}")


def _trade_log(frame: pd.DataFrame) -> pd.DataFrame:
    entries = frame.index[(frame["position"].diff() > 0)].tolist()
    exits = frame.index[(frame["position"].diff() < 0)].tolist()
    if frame["position"].iloc[0] > 0:
        entries.insert(0, frame.index[0])
    if entries and (not exits or exits[-1] < entries[-1]):
        exits.append(frame.index[-1])

    rows: list[dict[str, Any]] = []
    for number, entry_index in enumerate(entries, start=1):
        exit_index = next((candidate for candidate in exits if candidate > entry_index), frame.index[-1])
        slice_ = frame.loc[entry_index:exit_index]
        entry_price = float(frame.loc[entry_index, "close"])
        exit_price = float(frame.loc[exit_index, "close"])
        rows.append({
            "trade": number,
            "entry_date": frame.loc[entry_index, "date"],
            "exit_date": frame.loc[exit_index, "date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "return": float((1 + slice_["strategy_return"]).prod() - 1),
            "bars": int(len(slice_)),
        })
    return pd.DataFrame(rows, columns=["trade", "entry_date", "exit_date", "entry_price", "exit_price", "return", "bars"])


def _metrics(frame: pd.DataFrame, trade_log: pd.DataFrame | None = None) -> dict[str, float]:
    if frame.empty:
        return {name: 0.0 for name in (
            "total_return", "cagr", "volatility", "sharpe", "sortino", "max_drawdown",
            "win_rate", "trades", "exposure", "benchmark_return", "ending_equity",
        )}

    returns = frame["strategy_return"].astype(float)
    equity = frame["equity"].astype(float)
    total_return = equity.iloc[-1] / equity.iloc[0] - 1 if equity.iloc[0] else 0.0
    years = max(len(frame) / TRADING_DAYS, 1 / TRADING_DAYS)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if equity.iloc[0] > 0 and equity.iloc[-1] > 0 else -1.0
    volatility = returns.std(ddof=0) * np.sqrt(TRADING_DAYS)
    sharpe = returns.mean() / returns.std(ddof=0) * np.sqrt(TRADING_DAYS) if returns.std(ddof=0) > 0 else 0.0
    downside = returns[returns < 0]
    sortino = returns.mean() / downside.std(ddof=0) * np.sqrt(TRADING_DAYS) if len(downside) > 1 and downside.std(ddof=0) > 0 else 0.0
    if trade_log is None:
        trade_log = _trade_log(frame)
    completed = trade_log[trade_log["exit_date"] < frame["date"].iloc[-1]] if not trade_log.empty else trade_log
    wins = float((completed["return"] > 0).mean()) if not completed.empty else 0.0
    local_drawdown = equity / equity.cummax() - 1
    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "volatility": float(volatility),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": float(local_drawdown.min()),
        "win_rate": wins,
        "trades": float(len(trade_log)),
        "exposure": float(frame["position"].mean()),
        "benchmark_return": float(frame["benchmark"].iloc[-1] / frame["benchmark"].iloc[0] - 1),
        "ending_equity": float(equity.iloc[-1]),
    }


def run_backtest(
    data: pd.DataFrame,
    strategy: str,
    parameters: dict[str, float],
    starting_cash: float = 10_000,
    fee_bps: float = 5,
    train_percent: float = 0.70,
) -> BacktestResult:
    """Run a long/flat, next-bar backtest with explicit trading costs."""
    if len(data) < 60:
        raise ValueError("At least 60 price rows are required.")
    if starting_cash <= 0:
        raise ValueError("Starting capital must be positive.")
    if fee_bps < 0:
        raise ValueError("Trading costs cannot be negative.")
    if not 0.50 <= train_percent <= 0.90:
        raise ValueError("Training split must be between 50% and 90%.")

    frame = data.copy().reset_index(drop=True)
    frame["return"] = frame["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["signal"] = strategy_signal(frame, strategy, parameters)
    frame["position"] = frame["signal"].shift(1).fillna(0.0)
    frame["turnover"] = frame["position"].diff().abs().fillna(frame["position"].abs())
    frame["cost"] = frame["turnover"] * fee_bps / 10_000
    frame["strategy_return"] = frame["position"] * frame["return"] - frame["cost"]
    frame["equity"] = starting_cash * (1 + frame["strategy_return"]).cumprod()
    frame["benchmark"] = starting_cash * (1 + frame["return"]).cumprod()
    frame["drawdown"] = frame["equity"] / frame["equity"].cummax() - 1
    split_index = max(1, min(len(frame) - 1, int(len(frame) * train_percent)))
    frame["segment"] = np.where(frame.index < split_index, "Train", "Test")

    trades = _trade_log(frame)
    train_frame = frame.iloc[:split_index].copy()
    test_frame = frame.iloc[split_index:].copy()
    train_trades = _trade_log(train_frame)
    test_trades = _trade_log(test_frame)
    return BacktestResult(
        frame=frame,
        metrics=_metrics(frame, trades),
        train_metrics=_metrics(train_frame, train_trades),
        test_metrics=_metrics(test_frame, test_trades),
        trade_log=trades,
        strategy=strategy,
        parameters=dict(parameters),
    )


def parameter_sweep(
    data: pd.DataFrame,
    strategy: str,
    starting_cash: float,
    fee_bps: float,
    train_percent: float,
) -> pd.DataFrame:
    """Evaluate a compact parameter grid and rank it on training Sharpe.

    Test metrics are reported but deliberately excluded from ranking so the
    held-out segment remains a verification set instead of an optimizer.
    """
    candidates: list[dict[str, float]] = []
    if strategy == "Moving Average Crossover":
        for fast in (10, 20, 40, 60):
            for slow in (80, 120, 160, 220):
                if fast < slow:
                    candidates.append({"fast": fast, "slow": slow})
    elif strategy == "RSI Mean Reversion":
        for period in (7, 14, 21, 28):
            for entry in (20, 25, 30, 35):
                candidates.append({"period": period, "entry": entry, "exit": 55})
    elif strategy == "Price Breakout":
        for entry_window in (20, 40, 60, 90):
            for exit_window in (10, 20, 30, 45):
                candidates.append({"entry_window": entry_window, "exit_window": exit_window})
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    rows: list[dict[str, float]] = []
    for parameters in candidates:
        result = run_backtest(data, strategy, parameters, starting_cash, fee_bps, train_percent)
        rows.append({
            **parameters,
            "train_sharpe": result.train_metrics["sharpe"],
            "test_sharpe": result.test_metrics["sharpe"],
            "test_return": result.test_metrics["total_return"],
            "max_drawdown": result.test_metrics["max_drawdown"],
            "trades": result.test_metrics["trades"],
        })
    return pd.DataFrame(rows).sort_values(["train_sharpe", "test_sharpe"], ascending=False).reset_index(drop=True)
