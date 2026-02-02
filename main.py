"""
Main Orchestrator for the Hybrid Regime-Switching Trading Bot.
Runs the main trading loop, switching strategies based on market regime.
"""

import sys
import time
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import config
from src.database import (
    create_trade,
    close_trade,
    get_open_trade_by_strategy,
    StrategyType,
    TradeSide,
)
from src.exchange_client import ExchangeClient, Position
from src.watchman import Watchman, MarketRegime
from src.strategies.base_strategy import BaseStrategy, Signal, PositionInfo, SignalType
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.trend_follower import TrendSniperStrategy


class RegimeContextFilter(logging.Filter):
    """Logging filter to add regime and strategy context."""
    
    def __init__(self):
        super().__init__()
        self.regime = "UNKNOWN"
        self.strategy = "NONE"
    
    def filter(self, record):
        record.regime = self.regime
        record.strategy = self.strategy
        return True


def setup_logging() -> tuple[logging.Logger, RegimeContextFilter]:
    """
    Configure structured logging with console and file handlers.
    
    Returns:
        Tuple of (logger, context_filter)
    """
    # Create logger
    logger = logging.getLogger("trading_bot")
    logger.setLevel(getattr(logging, config.logging.log_level.upper()))
    
    # Create context filter
    context_filter = RegimeContextFilter()
    
    # Log format
    log_format = (
        "%(asctime)s - [REGIME: %(regime)s] - [STRATEGY: %(strategy)s] - "
        "%(levelname)s - %(message)s"
    )
    formatter = logging.Formatter(log_format)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    log_file = config.logging.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    logger.addHandler(file_handler)
    
    return logger, context_filter


class TradingBot:
    """
    Main trading bot orchestrator.
    
    Responsibilities:
    - Detect market regime using Watchman
    - Execute appropriate strategy based on regime
    - Manage cooldown after regime changes
    - Handle positions from inactive strategies
    """
    
    def __init__(self):
        """Initialize the trading bot."""
        self.logger, self.log_filter = setup_logging()
        
        self.logger.info("=" * 60)
        self.logger.info("HYBRID REGIME-SWITCHING TRADING BOT")
        self.logger.info("=" * 60)
        
        # Initialize components
        self.exchange = ExchangeClient()
        self.watchman = Watchman()
        
        # Initialize strategies
        self.mean_reversion = MeanReversionStrategy()
        self.trend_sniper = TrendSniperStrategy()
        
        # Track active positions
        self.positions: dict[str, PositionInfo] = {}
        
        self._log_config()
    
    def _log_config(self):
        """Log current configuration."""
        self.logger.info(f"Trading Pair: {config.trading.trading_pair}")
        self.logger.info(f"Dry Run Mode: {config.trading.dry_run}")
        self.logger.info(f"Exchange: {config.exchange.exchange_id} (Sandbox: {config.exchange.sandbox})")
        self.logger.info(f"Position Size: {config.trading.position_size_percent}%")
        self.logger.info(f"ADX Thresholds: Trend>{config.watchman.adx_trend_start}, Range<{config.watchman.adx_range_return}")
        self.logger.info(f"Cooldown: {config.watchman.cooldown_seconds}s")
        self.logger.info("-" * 60)
    
    def _get_active_strategy(self, regime: MarketRegime) -> BaseStrategy:
        """Get the strategy for the current regime."""
        if regime == MarketRegime.RANGING:
            return self.mean_reversion
        return self.trend_sniper
    
    def _get_strategy_type(self, strategy: BaseStrategy) -> StrategyType:
        """Convert strategy to enum for database."""
        if isinstance(strategy, MeanReversionStrategy):
            return StrategyType.MEAN_REVERSION
        return StrategyType.TREND_SNIPER
    
    def _update_log_context(self, regime: MarketRegime, strategy: Optional[BaseStrategy]):
        """Update logging context."""
        self.log_filter.regime = regime.value
        self.log_filter.strategy = strategy.name if strategy else "NONE"
    
    def _fetch_data_for_strategy(self, strategy: BaseStrategy):
        """Fetch OHLCV data for a strategy's timeframe."""
        return self.exchange.fetch_ohlcv(
            symbol=config.trading.trading_pair,
            timeframe=strategy.timeframe,
            limit=300
        )
    
    def _fetch_watchman_data(self):
        """Fetch OHLCV data for watchman (1h timeframe)."""
        return self.exchange.fetch_ohlcv(
            symbol=config.trading.trading_pair,
            timeframe=Watchman.TIMEFRAME,
            limit=100
        )
    
    def _handle_entry(self, strategy: BaseStrategy, signal: Signal):
        """Handle a new trade entry."""
        symbol = config.trading.trading_pair
        side = 'buy' if signal.signal_type == SignalType.LONG else 'sell'
        trade_side = TradeSide.LONG if signal.signal_type == SignalType.LONG else TradeSide.SHORT
        
        # Calculate position size
        position_size = self.exchange.calculate_position_size(
            symbol=symbol,
            side=signal.signal_type.value.lower(),
            stop_loss_price=signal.stop_loss
        )
        
        if position_size <= 0:
            self.logger.warning("Position size too small, skipping entry")
            return
        
        # Log signal
        indicator_str = ", ".join(f"{k}={v}" for k, v in signal.indicators.items())
        self.logger.info(
            f"SIGNAL GENERATED | Symbol: {symbol} | Side: {signal.signal_type.value} | "
            f"Price: {signal.entry_price:.2f} | Ind: {indicator_str} | "
            f"Reason: {signal.reason}"
        )
        
        # Execute order
        order = self.exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=position_size
        )
        
        # Create trade record
        trade = create_trade(
            symbol=symbol,
            strategy=self._get_strategy_type(strategy),
            side=trade_side,
            entry_price=order.get('price', signal.entry_price),
            size=position_size
        )
        
        # Track position
        self.positions[strategy.name] = PositionInfo(
            trade_id=trade.id,
            symbol=symbol,
            side=signal.signal_type.value,
            entry_price=order.get('price', signal.entry_price),
            size=position_size,
            stop_loss=signal.stop_loss
        )
        
        self.logger.info(
            f"POSITION OPENED | Trade ID: {trade.id} | Size: {position_size:.6f} | "
            f"Entry: {signal.entry_price:.2f} | SL: {signal.stop_loss:.2f}"
        )
    
    def _handle_exit(self, strategy: BaseStrategy, reason: str):
        """Handle position exit."""
        position = self.positions.get(strategy.name)
        if not position:
            return
        
        symbol = config.trading.trading_pair
        current_price = self.exchange.get_current_price(symbol)
        
        # Create exchange position object
        exchange_position = Position(
            symbol=symbol,
            side=position.side.lower(),
            size=position.size,
            entry_price=position.entry_price
        )
        
        # Close position on exchange
        self.exchange.close_position(symbol, exchange_position)
        
        # Update trade record
        trade = close_trade(
            trade_id=position.trade_id,
            exit_price=current_price
        )
        
        self.logger.info(
            f"POSITION CLOSED | Trade ID: {position.trade_id} | Exit: {current_price:.2f} | "
            f"PnL: ${trade.pnl_absolute:.2f} ({trade.pnl_percent * 100:.2f}%) | "
            f"Reason: {reason}"
        )
        
        # Remove from tracking
        del self.positions[strategy.name]
    
    def _manage_position(self, strategy: BaseStrategy, is_active: bool):
        """
        Manage existing position for a strategy.
        
        If strategy is inactive (wrong regime), only check exits.
        If strategy is active, check both entries and exits.
        """
        position = self.positions.get(strategy.name)
        df = self._fetch_data_for_strategy(strategy)
        current_price = self.exchange.get_current_price(config.trading.trading_pair)
        
        if position:
            # Check exit conditions
            should_exit, reason = strategy.check_exit_signal(df, position, current_price)
            
            if should_exit:
                self._handle_exit(strategy, reason)
                return
            
            # Update trailing stop for trend strategy
            if isinstance(strategy, TrendSniperStrategy):
                new_stop = strategy.update_trailing_stop(df, position)
                if new_stop != position.stop_loss:
                    self.logger.debug(f"Trailing stop updated: {position.stop_loss:.2f} -> {new_stop:.2f}")
                    position.stop_loss = new_stop
        
        elif is_active and not self.watchman.is_in_cooldown:
            # Check for new entry signals (only if active and not in cooldown)
            signal = strategy.check_entry_signal(df)
            
            if signal:
                self._handle_entry(strategy, signal)
    
    def run_iteration(self):
        """Run a single iteration of the trading loop."""
        try:
            # 1. Detect market regime
            watchman_data = self._fetch_watchman_data()
            regime, regime_changed = self.watchman.detect_regime(watchman_data)
            
            # Update log context
            active_strategy = self._get_active_strategy(regime)
            self._update_log_context(regime, active_strategy)
            
            # Log cooldown status if applicable
            if self.watchman.is_in_cooldown:
                self.logger.info(
                    f"COOLDOWN ACTIVE | Remaining: {self.watchman.cooldown_remaining}s | "
                    f"New entries blocked"
                )
            
            # 2. Manage positions for both strategies
            # Active strategy: can enter and exit
            # Inactive strategy: can only exit (let it manage its SL/TP)
            
            mr_active = regime == MarketRegime.RANGING
            ts_active = regime == MarketRegime.TRENDING
            
            self._manage_position(self.mean_reversion, is_active=mr_active)
            self._manage_position(self.trend_sniper, is_active=ts_active)
            
            # 3. Log status
            status = self.watchman.get_status()
            self.logger.debug(
                f"STATUS | ADX: {status['adx']} | Positions: MR={self.positions.get('MEAN_REVERSION') is not None}, "
                f"TS={self.positions.get('TREND_SNIPER') is not None}"
            )
            
        except Exception as e:
            self.logger.error(f"Error in trading loop: {e}", exc_info=True)
    
    def run(self):
        """Run the main trading loop."""
        self.logger.info("Starting main trading loop...")
        self.logger.info(f"Loop interval: {config.trading.loop_interval_seconds}s")
        
        while True:
            try:
                loop_start = time.time()
                
                self.run_iteration()
                
                # Sleep until next iteration
                elapsed = time.time() - loop_start
                sleep_time = max(0, config.trading.loop_interval_seconds - elapsed)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except KeyboardInterrupt:
                self.logger.info("Shutdown signal received. Exiting...")
                break
            except Exception as e:
                self.logger.error(f"Critical error in main loop: {e}", exc_info=True)
                self.logger.info(f"Retrying in {config.trading.loop_interval_seconds}s...")
                time.sleep(config.trading.loop_interval_seconds)


def main():
    """Entry point for the trading bot."""
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()
