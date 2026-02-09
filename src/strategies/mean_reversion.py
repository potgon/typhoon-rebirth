"""
Mean Reversion Strategy for the Hybrid Regime-Switching Trading Bot.
Active only during RANGING market regime.

Entry:
- Long: Close < Bollinger Lower Band AND RSI < 30
- Short: Close > Bollinger Upper Band AND RSI > 70

Exit:
- Price touches SMA(20) OR Stop Loss (1.5x ATR)
"""

from typing import Optional
import pandas as pd
import pandas_ta as ta

from src.config import config
from src.strategies.base_strategy import (
    BaseStrategy,
    Signal,
    SignalType,
    PositionInfo,
)


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion strategy using Bollinger Bands and RSI.
    Designed for ranging/sideways markets.
    """
    
    def __init__(self):
        """Initialize Mean Reversion strategy."""
        super().__init__(
            name="MEAN_REVERSION",
            timeframe=config.mean_reversion.timeframe
        )
        self.cfg = config.mean_reversion
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Bollinger Bands, RSI, SMA, and ATR.
        
        Args:
            df: DataFrame with OHLCV data
        
        Returns:
            DataFrame with indicator columns added
        """
        df = df.copy()
        
        # Bollinger Bands
        bbands = ta.bbands(
            df['close'],
            length=self.cfg.bb_period,
            std=self.cfg.bb_std_dev
        )
        # Dynamically find column names (pandas_ta formats std_dev inconsistently)
        bbl_col = [c for c in bbands.columns if c.startswith('BBL_')][0]
        bbm_col = [c for c in bbands.columns if c.startswith('BBM_')][0]
        bbu_col = [c for c in bbands.columns if c.startswith('BBU_')][0]
        df['bb_lower'] = bbands[bbl_col]
        df['bb_middle'] = bbands[bbm_col]
        df['bb_upper'] = bbands[bbu_col]
        
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=self.cfg.rsi_period)
        
        # SMA for exit signal (same as BB middle)
        df['sma'] = ta.sma(df['close'], length=self.cfg.bb_period)
        
        # ATR for stop loss
        df['atr'] = ta.atr(
            df['high'],
            df['low'],
            df['close'],
            length=self.cfg.atr_period
        )
        
        return df
    
    def check_entry_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """
        Check for mean reversion entry signals.
        
        Long Entry: Close < BB Lower AND RSI < 30 (oversold)
        Short Entry: Close > BB Upper AND RSI > 70 (overbought)
        """
        df = self.calculate_indicators(df)
        
        if df.empty or df['rsi'].isna().iloc[-1]:
            return None
        
        latest = df.iloc[-1]
        close = latest['close']
        rsi = latest['rsi']
        bb_lower = latest['bb_lower']
        bb_upper = latest['bb_upper']
        atr = latest['atr']
        
        indicators = {
            'RSI': round(rsi, 2),
            'BB_Lower': round(bb_lower, 2),
            'BB_Upper': round(bb_upper, 2),
            'Close': round(close, 2),
        }
        
        # Long signal: Oversold condition
        if close < bb_lower and rsi < self.cfg.rsi_oversold:
            stop_loss = self.calculate_stop_loss(df, SignalType.LONG, close)
            return Signal(
                signal_type=SignalType.LONG,
                entry_price=close,
                stop_loss=stop_loss,
                reason=f"Oversold Condition: Close ({close:.2f}) < BB_Low ({bb_lower:.2f}), RSI ({rsi:.1f}) < {self.cfg.rsi_oversold}",
                indicators=indicators
            )
        
        # Short signal: Overbought condition
        if close > bb_upper and rsi > self.cfg.rsi_overbought:
            stop_loss = self.calculate_stop_loss(df, SignalType.SHORT, close)
            return Signal(
                signal_type=SignalType.SHORT,
                entry_price=close,
                stop_loss=stop_loss,
                reason=f"Overbought Condition: Close ({close:.2f}) > BB_Upper ({bb_upper:.2f}), RSI ({rsi:.1f}) > {self.cfg.rsi_overbought}",
                indicators=indicators
            )
        
        return None
    
    def check_exit_signal(
        self,
        df: pd.DataFrame,
        position: PositionInfo,
        current_price: float
    ) -> tuple[bool, str]:
        """
        Check if position should be closed.
        
        Exit conditions:
        1. Price touches SMA(20)
        2. Stop Loss hit
        """
        df = self.calculate_indicators(df)
        
        if df.empty:
            return False, ""
        
        latest = df.iloc[-1]
        sma = latest['sma']
        
        # Check stop loss
        if position.side == 'LONG':
            if current_price <= position.stop_loss:
                return True, f"Stop Loss Hit: Price ({current_price:.2f}) <= SL ({position.stop_loss:.2f})"
            # Exit at SMA (take profit for long)
            if current_price >= sma:
                return True, f"Take Profit: Price ({current_price:.2f}) reached SMA ({sma:.2f})"
        else:  # SHORT
            if current_price >= position.stop_loss:
                return True, f"Stop Loss Hit: Price ({current_price:.2f}) >= SL ({position.stop_loss:.2f})"
            # Exit at SMA (take profit for short)
            if current_price <= sma:
                return True, f"Take Profit: Price ({current_price:.2f}) reached SMA ({sma:.2f})"
        
        return False, ""
    
    def calculate_stop_loss(
        self,
        df: pd.DataFrame,
        signal_type: SignalType,
        entry_price: float
    ) -> float:
        """
        Calculate stop loss using ATR.
        
        Stop Loss = Entry Price ± (ATR * multiplier)
        """
        if df.empty:
            # Fallback: 2% stop loss
            if signal_type == SignalType.LONG:
                return entry_price * 0.98
            return entry_price * 1.02
        
        latest = df.iloc[-1]
        atr = latest['atr'] if not pd.isna(latest['atr']) else entry_price * 0.02
        
        stop_distance = atr * self.cfg.atr_sl_multiplier
        
        if signal_type == SignalType.LONG:
            return entry_price - stop_distance
        else:  # SHORT
            return entry_price + stop_distance
