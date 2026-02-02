"""
Analysis Tool for the Hybrid Regime-Switching Trading Bot.
Standalone script to calculate and display trading performance metrics.

Usage: python -m src.analysis_tool
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from src.database import (
    get_all_closed_trades,
    get_trades_by_strategy,
    StrategyType,
    Trade
)


def calculate_metrics(trades: list[Trade]) -> dict:
    """
    Calculate performance metrics for a list of trades.
    
    Args:
        trades: List of closed Trade objects
    
    Returns:
        Dictionary with calculated metrics
    """
    if not trades:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'winrate': 0.0,
            'profit_factor': 0.0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
        }
    
    # Separate winning and losing trades
    winning = [t for t in trades if t.pnl_absolute and t.pnl_absolute > 0]
    losing = [t for t in trades if t.pnl_absolute and t.pnl_absolute <= 0]
    
    # Winrate
    total_trades = len(trades)
    winning_trades = len(winning)
    losing_trades = len(losing)
    winrate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    # Total PnL
    total_pnl = sum(t.pnl_absolute for t in trades if t.pnl_absolute)
    
    # Gross profit and loss
    gross_profit = sum(t.pnl_absolute for t in winning if t.pnl_absolute)
    gross_loss = abs(sum(t.pnl_absolute for t in losing if t.pnl_absolute))
    
    # Profit Factor
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0
    
    # Average win/loss
    avg_win = (gross_profit / winning_trades) if winning_trades > 0 else 0.0
    avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0.0
    
    # Best and worst trades
    pnl_values = [t.pnl_absolute for t in trades if t.pnl_absolute]
    best_trade = max(pnl_values) if pnl_values else 0.0
    worst_trade = min(pnl_values) if pnl_values else 0.0
    
    # Max Drawdown calculation
    max_drawdown = calculate_max_drawdown(trades)
    
    return {
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'winrate': winrate,
        'profit_factor': profit_factor,
        'total_pnl': total_pnl,
        'max_drawdown': max_drawdown,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
    }


def calculate_max_drawdown(trades: list[Trade]) -> float:
    """
    Calculate maximum drawdown from equity curve.
    
    Args:
        trades: List of closed Trade objects (ordered by exit time)
    
    Returns:
        Maximum drawdown as a percentage
    """
    if not trades:
        return 0.0
    
    # Sort trades by exit time
    sorted_trades = sorted(
        [t for t in trades if t.exit_time and t.pnl_absolute],
        key=lambda t: t.exit_time
    )
    
    if not sorted_trades:
        return 0.0
    
    # Build cumulative equity curve
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    
    for trade in sorted_trades:
        equity += trade.pnl_absolute
        peak = max(peak, equity)
        
        if peak > 0:
            drawdown = (peak - equity) / peak * 100
            max_dd = max(max_dd, drawdown)
    
    return max_dd


def format_currency(value: float) -> str:
    """Format value as currency."""
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    """Format value as percentage."""
    return f"{value:.2f}%"


def print_separator(char: str = "=", length: int = 60):
    """Print a separator line."""
    print(char * length)


def print_metrics(title: str, metrics: dict):
    """Print formatted metrics."""
    print_separator()
    print(f"  {title}")
    print_separator()
    
    if metrics['total_trades'] == 0:
        print("  No trades found.")
        return
    
    print(f"  Total Trades:    {metrics['total_trades']}")
    print(f"  Winning Trades:  {metrics['winning_trades']}")
    print(f"  Losing Trades:   {metrics['losing_trades']}")
    print()
    print(f"  Winrate:         {format_percent(metrics['winrate'])}")
    print(f"  Profit Factor:   {metrics['profit_factor']:.2f}")
    print()
    print(f"  Total PnL:       {format_currency(metrics['total_pnl'])}")
    print(f"  Max Drawdown:    {format_percent(metrics['max_drawdown'])}")
    print()
    print(f"  Avg Win:         {format_currency(metrics['avg_win'])}")
    print(f"  Avg Loss:        {format_currency(metrics['avg_loss'])}")
    print(f"  Best Trade:      {format_currency(metrics['best_trade'])}")
    print(f"  Worst Trade:     {format_currency(metrics['worst_trade'])}")


def main():
    """Main entry point for analysis tool."""
    print()
    print_separator("=", 60)
    print("  HYBRID REGIME-SWITCHING BOT - PERFORMANCE ANALYSIS")
    print(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print_separator("=", 60)
    print()
    
    # Get all closed trades
    all_trades = get_all_closed_trades()
    
    # Overall metrics
    overall_metrics = calculate_metrics(all_trades)
    print_metrics("OVERALL PERFORMANCE", overall_metrics)
    print()
    
    # Mean Reversion metrics
    mr_trades = get_trades_by_strategy(StrategyType.MEAN_REVERSION)
    mr_metrics = calculate_metrics(mr_trades)
    print_metrics("MEAN REVERSION STRATEGY", mr_metrics)
    print()
    
    # Trend Sniper metrics
    ts_trades = get_trades_by_strategy(StrategyType.TREND_SNIPER)
    ts_metrics = calculate_metrics(ts_trades)
    print_metrics("TREND SNIPER STRATEGY", ts_metrics)
    print()
    
    print_separator()
    print("  Analysis complete.")
    print_separator()


if __name__ == "__main__":
    main()
