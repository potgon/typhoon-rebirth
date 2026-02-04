"""
Exchange client module for the Hybrid Regime-Switching Trading Bot.
CCXT wrapper with retry logic and error handling.
"""

import time
import logging
from typing import Optional
from dataclasses import dataclass

import ccxt
import pandas as pd

from src.config import config

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents an open position."""
    symbol: str
    side: str  # 'long' or 'short'
    size: float
    entry_price: float
    unrealized_pnl: float = 0.0


class ExchangeClient:
    """
    CCXT wrapper with automatic retry logic for network errors.
    
    NOTE: Binance has deprecated testnet/sandbox for futures.
    For paper trading, use DRY_RUN=true or get demo API keys from Binance.
    When sandbox=true, we now use SPOT market instead of futures.
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5
    
    def __init__(self):
        """Initialize the exchange client."""
        self.use_futures = self._should_use_futures()
        self.exchange = self._create_exchange()
        self._load_markets()
    
    def _should_use_futures(self) -> bool:
        """
        Determine if we can use futures market.
        
        Binance deprecated testnet for futures, so if sandbox mode is enabled,
        we fall back to spot market to avoid errors.
        """
        if config.exchange.sandbox:
            logger.warning(
                "Sandbox mode enabled - using SPOT market instead of futures. "
                "Binance deprecated testnet for futures. "
                "For futures paper trading, use DRY_RUN=true with real API keys, "
                "or get demo trading API keys from Binance."
            )
            return False
        return True
    
    def _create_exchange(self) -> ccxt.Exchange:
        """Create and configure the CCXT exchange instance."""
        exchange_class = getattr(ccxt, config.exchange.exchange_id)
        
        market_type = 'future' if self.use_futures else 'spot'
        
        exchange_config = {
            'apiKey': config.exchange.api_key,
            'secret': config.exchange.secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': market_type,
            }
        }
        
        # Only enable sandbox for spot (futures sandbox is deprecated)
        if config.exchange.sandbox and not self.use_futures:
            exchange_config['sandbox'] = True
        
        exchange = exchange_class(exchange_config)
        
        # Set sandbox mode only for spot
        if config.exchange.sandbox and not self.use_futures:
            exchange.set_sandbox_mode(True)
            logger.info(f"Exchange initialized in SANDBOX mode (SPOT market)")
        else:
            mode = "FUTURES" if self.use_futures else "SPOT"
            dry_run_status = "DRY_RUN enabled" if config.trading.dry_run else "LIVE TRADING"
            logger.info(f"Exchange initialized: {mode} market, {dry_run_status}")
        
        return exchange
    
    def _load_markets(self):
        """Load market data with retry."""
        self._retry_operation(lambda: self.exchange.load_markets())
        logger.info(f"Loaded {len(self.exchange.markets)} markets")
    
    def _retry_operation(self, operation, max_retries: int = None):
        """Execute operation with exponential backoff retry."""
        max_retries = max_retries or self.MAX_RETRIES
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                return operation()
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable) as e:
                last_exception = e
                wait_time = self.RETRY_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    f"Network error on attempt {attempt + 1}/{max_retries}: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error: {e}")
                raise
        
        logger.error(f"Max retries exceeded. Last error: {last_exception}")
        raise last_exception
    
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candlestick data.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '15m', '1h')
            limit: Number of candles to fetch
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        ohlcv = self._retry_operation(
            lambda: self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        )
        
        df = pd.DataFrame(
            ohlcv,
            columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
        )
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        return df
    
    def get_ticker(self, symbol: str) -> dict:
        """Get current ticker data for a symbol."""
        return self._retry_operation(
            lambda: self.exchange.fetch_ticker(symbol)
        )
    
    def get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        ticker = self.get_ticker(symbol)
        return ticker['last']
    
    def get_balance(self, currency: str = 'USDT') -> float:
        """
        Get available balance for a currency.
        
        In DRY_RUN mode with SIMULATED_BALANCE > 0, uses the PaperTradingManager
        which tracks dynamic balance as trades are opened/closed.
        """
        # Use dynamic paper trading balance
        if config.trading.dry_run and config.trading.simulated_balance > 0:
            from src.paper_trading import get_paper_manager
            return get_paper_manager().get_balance()
        
        balance = self._retry_operation(
            lambda: self.exchange.fetch_balance()
        )
        return balance.get(currency, {}).get('free', 0.0)
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol (futures only)."""
        # Spot market doesn't have position tracking
        if not self.use_futures:
            return None
        
        try:
            positions = self._retry_operation(
                lambda: self.exchange.fetch_positions([symbol])
            )
            
            for pos in positions:
                if pos['symbol'] == symbol and abs(pos['contracts']) > 0:
                    return Position(
                        symbol=symbol,
                        side='long' if pos['side'] == 'long' else 'short',
                        size=abs(pos['contracts']),
                        entry_price=pos['entryPrice'],
                        unrealized_pnl=pos.get('unrealizedPnl', 0.0)
                    )
            return None
        except ccxt.NotSupported:
            # Spot trading doesn't have positions
            return None
    
    def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        reduce_only: bool = False
    ) -> dict:
        """
        Create a market order.
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            amount: Order amount in base currency
            reduce_only: If True, only reduces position
        
        Returns:
            Order response from exchange
        """
        if config.trading.dry_run:
            logger.info(
                f"DRY RUN: Would create {side} market order for {amount} {symbol}"
            )
            return {
                'id': 'dry_run_order',
                'symbol': symbol,
                'side': side,
                'amount': amount,
                'price': self.get_current_price(symbol),
                'status': 'closed',
                'dry_run': True
            }
        
        params = {'reduceOnly': reduce_only} if reduce_only else {}
        
        order = self._retry_operation(
            lambda: self.exchange.create_market_order(
                symbol, side, amount, params=params
            )
        )
        
        logger.info(
            f"Created {side} market order: {amount} {symbol} @ {order.get('price', 'market')}"
        )
        return order
    
    def calculate_position_size(
        self,
        symbol: str,
        side: str,
        stop_loss_price: float
    ) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            symbol: Trading pair
            side: 'long' or 'short'
            stop_loss_price: Stop loss price level
        
        Returns:
            Position size in base currency
        """
        balance = self.get_balance('USDT')
        current_price = self.get_current_price(symbol)
        
        # Position size based on percentage of capital
        position_value = balance * (config.trading.position_size_percent / 100)
        position_size = position_value / current_price
        
        # Get minimum order size from exchange
        market = self.exchange.market(symbol)
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)
        
        if position_size < min_amount:
            logger.warning(
                f"Calculated position size {position_size} below minimum {min_amount}"
            )
            return 0.0
        
        return position_size
    
    def close_position(self, symbol: str, position: Position) -> dict:
        """Close an existing position."""
        side = 'sell' if position.side == 'long' else 'buy'
        return self.create_market_order(
            symbol=symbol,
            side=side,
            amount=position.size,
            reduce_only=True
        )
