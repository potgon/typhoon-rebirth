"""
Watchman - Market Regime Detector for the Hybrid Regime-Switching Trading Bot.
Uses ADX indicator with hysteresis to detect TRENDING vs RANGING market conditions.
"""

import logging
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pandas_ta as ta

from src.config import config

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime types."""
    RANGING = "RANGING"
    TRENDING = "TRENDING"


class Watchman:
    """
    Market regime detector using ADX with hysteresis.
    
    Hysteresis prevents rapid switching when ADX oscillates around thresholds:
    - RANGING -> TRENDING: only when ADX > ADX_TREND_START (25)
    - TRENDING -> RANGING: only when ADX < ADX_RANGE_RETURN (20)
    
    This creates a "buffer zone" between 20-25 where the previous state is maintained.
    """
    
    # Timeframe for regime analysis
    TIMEFRAME = "1h"
    
    def __init__(self):
        """Initialize the Watchman."""
        self.cfg = config.watchman
        self._current_regime: MarketRegime = MarketRegime.RANGING
        self._last_regime_change: Optional[datetime] = None
        self._last_adx_value: float = 0.0
    
    @property
    def current_regime(self) -> MarketRegime:
        """Get the current market regime."""
        return self._current_regime
    
    @property
    def last_adx(self) -> float:
        """Get the last calculated ADX value."""
        return self._last_adx_value
    
    @property
    def is_in_cooldown(self) -> bool:
        """Check if we're in cooldown period after a regime change."""
        if self._last_regime_change is None:
            return False
        
        cooldown_end = self._last_regime_change + timedelta(
            seconds=self.cfg.cooldown_seconds
        )
        return datetime.utcnow() < cooldown_end
    
    @property
    def cooldown_remaining(self) -> int:
        """Get remaining cooldown seconds (0 if not in cooldown)."""
        if not self.is_in_cooldown:
            return 0
        
        cooldown_end = self._last_regime_change + timedelta(
            seconds=self.cfg.cooldown_seconds
        )
        remaining = (cooldown_end - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))
    
    def calculate_adx(self, df: pd.DataFrame) -> float:
        """
        Calculate ADX indicator.
        
        Args:
            df: DataFrame with OHLCV data (1h timeframe)
        
        Returns:
            Current ADX value
        """
        if df.empty or len(df) < self.cfg.adx_period + 1:
            logger.warning(f"Insufficient data for ADX calculation: {len(df)} candles")
            return 0.0
        
        adx_result = ta.adx(
            df['high'],
            df['low'],
            df['close'],
            length=self.cfg.adx_period
        )
        
        adx_column = f'ADX_{self.cfg.adx_period}'
        if adx_column not in adx_result.columns:
            logger.error(f"ADX column not found in result: {adx_result.columns.tolist()}")
            return 0.0
        
        adx_value = adx_result[adx_column].iloc[-1]
        
        if pd.isna(adx_value):
            logger.warning("ADX value is NaN")
            return self._last_adx_value
        
        self._last_adx_value = adx_value
        return adx_value
    
    def detect_regime(self, df: pd.DataFrame) -> tuple[MarketRegime, bool]:
        """
        Detect current market regime with hysteresis.
        
        Args:
            df: DataFrame with OHLCV data (1h timeframe)
        
        Returns:
            Tuple of (current_regime, regime_changed)
        """
        adx = self.calculate_adx(df)
        previous_regime = self._current_regime
        regime_changed = False
        
        # Hysteresis logic
        if self._current_regime == MarketRegime.RANGING:
            # Only switch to TRENDING if ADX > trend_start threshold
            if adx > self.cfg.adx_trend_start:
                self._current_regime = MarketRegime.TRENDING
                regime_changed = True
                self._last_regime_change = datetime.utcnow()
                
                logger.info(
                    f"REGIME CHANGE DETECTED | Old: {previous_regime.value} | "
                    f"New: {self._current_regime.value} | ADX Value: {adx:.2f} | "
                    f"Action: Activating Trend Sniper Strategy"
                )
        
        elif self._current_regime == MarketRegime.TRENDING:
            # Only switch back to RANGING if ADX < range_return threshold
            if adx < self.cfg.adx_range_return:
                self._current_regime = MarketRegime.RANGING
                regime_changed = True
                self._last_regime_change = datetime.utcnow()
                
                logger.info(
                    f"REGIME CHANGE DETECTED | Old: {previous_regime.value} | "
                    f"New: {self._current_regime.value} | ADX Value: {adx:.2f} | "
                    f"Action: Activating Mean Reversion Strategy"
                )
        
        if not regime_changed:
            logger.debug(
                f"Regime check | Current: {self._current_regime.value} | "
                f"ADX: {adx:.2f} | Thresholds: [{self.cfg.adx_range_return}, {self.cfg.adx_trend_start}]"
            )
        
        return self._current_regime, regime_changed
    
    def get_status(self) -> dict:
        """Get current watchman status for logging."""
        return {
            'regime': self._current_regime.value,
            'adx': round(self._last_adx_value, 2),
            'in_cooldown': self.is_in_cooldown,
            'cooldown_remaining': self.cooldown_remaining,
            'thresholds': {
                'trend_start': self.cfg.adx_trend_start,
                'range_return': self.cfg.adx_range_return,
            }
        }
