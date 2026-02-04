"""
Configuration module for the Hybrid Regime-Switching Trading Bot.
Loads and validates environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


def get_env(key: str, default: str | None = None, required: bool = False) -> str:
    """Get environment variable with optional default and validation."""
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on")


def get_env_int(key: str, default: int) -> int:
    """Get integer environment variable."""
    return int(os.getenv(key, str(default)))


def get_env_float(key: str, default: float) -> float:
    """Get float environment variable."""
    return float(os.getenv(key, str(default)))


@dataclass
class ExchangeConfig:
    """Exchange connection configuration."""
    exchange_id: str
    api_key: str
    secret: str
    sandbox: bool
    
    @classmethod
    def from_env(cls) -> "ExchangeConfig":
        return cls(
            exchange_id=get_env("EXCHANGE_ID", "binance"),
            api_key=get_env("EXCHANGE_API_KEY", ""),
            secret=get_env("EXCHANGE_SECRET", ""),
            sandbox=get_env_bool("EXCHANGE_SANDBOX", True),
        )


@dataclass
class WatchmanConfig:
    """Watchman (regime detection) configuration."""
    adx_period: int
    adx_trend_start: float
    adx_range_return: float
    cooldown_seconds: int
    
    @classmethod
    def from_env(cls) -> "WatchmanConfig":
        return cls(
            adx_period=get_env_int("ADX_PERIOD", 14),
            adx_trend_start=get_env_float("ADX_TREND_START", 25.0),
            adx_range_return=get_env_float("ADX_RANGE_RETURN", 20.0),
            cooldown_seconds=get_env_int("REGIME_COOLDOWN_SECONDS", 900),
        )


@dataclass
class MeanReversionConfig:
    """Mean Reversion strategy configuration."""
    timeframe: str
    bb_period: int
    bb_std_dev: float
    rsi_period: int
    rsi_oversold: float
    rsi_overbought: float
    atr_period: int
    atr_sl_multiplier: float
    
    @classmethod
    def from_env(cls) -> "MeanReversionConfig":
        return cls(
            timeframe=get_env("MEAN_REVERSION_TIMEFRAME", "15m"),
            bb_period=get_env_int("BB_PERIOD", 20),
            bb_std_dev=get_env_float("BB_STD_DEV", 2.0),
            rsi_period=get_env_int("RSI_PERIOD", 14),
            rsi_oversold=get_env_float("RSI_OVERSOLD", 30.0),
            rsi_overbought=get_env_float("RSI_OVERBOUGHT", 70.0),
            atr_period=get_env_int("ATR_PERIOD", 14),
            atr_sl_multiplier=get_env_float("ATR_SL_MULTIPLIER", 1.5),
        )


@dataclass
class TrendSniperConfig:
    """Trend Sniper strategy configuration."""
    timeframe: str
    donchian_period: int
    ema_period: int
    
    @classmethod
    def from_env(cls) -> "TrendSniperConfig":
        return cls(
            timeframe=get_env("TREND_TIMEFRAME", "1h"),
            donchian_period=get_env_int("DONCHIAN_PERIOD", 20),
            ema_period=get_env_int("EMA_PERIOD", 200),
        )


@dataclass
class TradingConfig:
    """General trading configuration."""
    trading_pair: str
    position_size_percent: float
    min_profit_threshold: float
    max_drawdown: float
    loop_interval_seconds: int
    dry_run: bool
    simulated_balance: float  # Starting balance for paper trading (0 = use real balance)
    
    @classmethod
    def from_env(cls) -> "TradingConfig":
        return cls(
            trading_pair=get_env("TRADING_PAIR", "BTC/USDT"),
            position_size_percent=get_env_float("POSITION_SIZE_PERCENT", 5.0),
            min_profit_threshold=get_env_float("MIN_PROFIT_THRESHOLD", 0.002),
            max_drawdown=get_env_float("MAX_DRAWDOWN", 0.1),
            loop_interval_seconds=get_env_int("LOOP_INTERVAL_SECONDS", 60),
            dry_run=get_env_bool("DRY_RUN", True),
            simulated_balance=get_env_float("SIMULATED_BALANCE", 0.0),
        )


@dataclass
class LoggingConfig:
    """Logging configuration."""
    log_level: str
    log_file: Path
    database_path: Path
    
    @classmethod
    def from_env(cls) -> "LoggingConfig":
        return cls(
            log_level=get_env("LOG_LEVEL", "INFO"),
            log_file=Path(get_env("LOG_FILE", "data/bot_activity.log")),
            database_path=Path(get_env("DATABASE_PATH", "data/bot_data.db")),
        )


@dataclass
class BotConfig:
    """Main configuration container for all bot settings."""
    exchange: ExchangeConfig
    watchman: WatchmanConfig
    mean_reversion: MeanReversionConfig
    trend_sniper: TrendSniperConfig
    trading: TradingConfig
    logging: LoggingConfig
    
    @classmethod
    def from_env(cls) -> "BotConfig":
        """Load all configuration from environment."""
        return cls(
            exchange=ExchangeConfig.from_env(),
            watchman=WatchmanConfig.from_env(),
            mean_reversion=MeanReversionConfig.from_env(),
            trend_sniper=TrendSniperConfig.from_env(),
            trading=TradingConfig.from_env(),
            logging=LoggingConfig.from_env(),
        )


# Global configuration instance
config = BotConfig.from_env()
