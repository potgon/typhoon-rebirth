"""
Trend Sniper Strategy for the Hybrid Regime-Switching Trading Bot.
Active only during TRENDING market regime.

Entry:
- Long: Price > Donchian High AND Price > EMA(200)
- Short: Price < Donchian Low AND Price < EMA(200)

Exit:
- Trailing Stop using opposite Donchian band
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


class TrendSniperStrategy(BaseStrategy):
    """
    Trend Following strategy using Donchian Channels and EMA filter.
    Designed for trending markets.
    """
    
    def __init__(self):
        """Initialize Trend Sniper strategy."""
        super().__init__(
            name="TREND_SNIPER",
            timeframe=config.trend_sniper.timeframe
        )
        self.cfg = config.trend_sniper
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate Donchian Channels and EMA.
        
        Args:
            df: DataFrame with OHLCV data
        
        Returns:
            DataFrame with indicator columns added
        """
        df = df.copy()
        
        # Donchian Channels
        donchian = ta.donchian(
            df['high'],
            df['low'],
            lower_length=self.cfg.donchian_period,
            upper_length=self.cfg.donchian_period
        )
        df['donchian_high'] = donchian[f'DCU_{self.cfg.donchian_period}_{self.cfg.donchian_period}']
        df['donchian_low'] = donchian[f'DCL_{self.cfg.donchian_period}_{self.cfg.donchian_period}']
        df['donchian_mid'] = donchian[f'DCM_{self.cfg.donchian_period}_{self.cfg.donchian_period}']
        
        # EMA filter
        df['ema'] = ta.ema(df['close'], length=self.cfg.ema_period)
        
        # Previous Donchian values for breakout detection
        df['prev_donchian_high'] = df['donchian_high'].shift(1)
        df['prev_donchian_low'] = df['donchian_low'].shift(1)
        
        return df
    
    def check_entry_signal(self, df: pd.DataFrame) -> Optional[Signal]:
        """
        Check for trend breakout entry signals.
        
        Long Entry: Close > Previous Donchian High AND Close > EMA(200)
        Short Entry: Close < Previous Donchian Low AND Close < EMA(200)
        """
        df = self.calculate_indicators(df)
        
        if df.empty or len(df) < self.cfg.ema_period + 1:
            return None
        
        latest = df.iloc[-1]
        
        # Skip if indicators not calculated yet
        if pd.isna(latest['ema']) or pd.isna(latest['prev_donchian_high']):
            return None
        
        close = latest['close']
        ema = latest['ema']
        prev_donchian_high = latest['prev_donchian_high']
        prev_donchian_low = latest['prev_donchian_low']
        donchian_high = latest['donchian_high']
        donchian_low = latest['donchian_low']
        
        indicators = {
            'Close': round(close, 2),
            'EMA_200': round(ema, 2),
            'Donchian_High': round(donchian_high, 2),
            'Donchian_Low': round(donchian_low, 2),
        }
        
        # Long signal: Breakout above Donchian High with EMA filter
        if close > prev_donchian_high and close > ema:
            stop_loss = self.calculate_stop_loss(df, SignalType.LONG, close)
            return Signal(
                signal_type=SignalType.LONG,
                entry_price=close,
                stop_loss=stop_loss,
                reason=f"Bullish Breakout: Close ({close:.2f}) > Donchian_High ({prev_donchian_high:.2f}), above EMA ({ema:.2f})",
                indicators=indicators
            )
        
        # Short signal: Breakout below Donchian Low with EMA filter
        if close < prev_donchian_low and close < ema:
            stop_loss = self.calculate_stop_loss(df, SignalType.SHORT, close)
            return Signal(
                signal_type=SignalType.SHORT,
                entry_price=close,
                stop_loss=stop_loss,
                reason=f"Bearish Breakout: Close ({close:.2f}) < Donchian_Low ({prev_donchian_low:.2f}), below EMA ({ema:.2f})",
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
        Check if position should be closed using trailing stop.
        
        Exit conditions:
        - Long: Price touches Donchian Low (trailing stop)
        - Short: Price touches Donchian High (trailing stop)
        """
        df = self.calculate_indicators(df)
        
        if df.empty:
            return False, ""
        
        latest = df.iloc[-1]
        donchian_high = latest['donchian_high']
        donchian_low = latest['donchian_low']
        
        if position.side == 'LONG':
            # Trailing stop at Donchian Low
            if current_price <= donchian_low:
                return True, f"Trailing Stop: Price ({current_price:.2f}) <= Donchian_Low ({donchian_low:.2f})"
        else:  # SHORT
            # Trailing stop at Donchian High
            if current_price >= donchian_high:
                return True, f"Trailing Stop: Price ({current_price:.2f}) >= Donchian_High ({donchian_high:.2f})"
        
        return False, ""
    
    def calculate_stop_loss(
        self,
        df: pd.DataFrame,
        signal_type: SignalType,
        entry_price: float
    ) -> float:
        """
        Calculate initial stop loss using Donchian Channel opposite band.
        
        Long: Stop at Donchian Low
        Short: Stop at Donchian High
        """
        if df.empty:
            # Fallback: 3% stop loss for trend trades
            if signal_type == SignalType.LONG:
                return entry_price * 0.97
            return entry_price * 1.03
        
        latest = df.iloc[-1]
        
        if signal_type == SignalType.LONG:
            stop_loss = latest['donchian_low']
            if pd.isna(stop_loss):
                stop_loss = entry_price * 0.97
        else:  # SHORT
            stop_loss = latest['donchian_high']
            if pd.isna(stop_loss):
                stop_loss = entry_price * 1.03
        
        return stop_loss
    
    def update_trailing_stop(
        self,
        df: pd.DataFrame,
        position: PositionInfo
    ) -> float:
        """
        Update trailing stop based on current Donchian values.
        
        Args:
            df: DataFrame with calculated indicators
            position: Current position info
        
        Returns:
            New trailing stop price
        """
        df = self.calculate_indicators(df)
        
        if df.empty:
            return position.stop_loss
        
        latest = df.iloc[-1]
        
        if position.side == 'LONG':
            new_stop = latest['donchian_low']
            # Only move stop up, never down
            return max(new_stop, position.stop_loss) if not pd.isna(new_stop) else position.stop_loss
        else:  # SHORT
            new_stop = latest['donchian_high']
            # Only move stop down, never up
            return min(new_stop, position.stop_loss) if not pd.isna(new_stop) else position.stop_loss
