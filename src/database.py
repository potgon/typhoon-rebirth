"""
Database module for the Hybrid Regime-Switching Trading Bot.
Handles SQLite persistence using SQLAlchemy ORM.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum as SQLEnum
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from contextlib import contextmanager
import enum
import threading

from src.config import config

# Thread-safe session factory
_engine = None
_SessionFactory = None
_lock = threading.Lock()

Base = declarative_base()


class TradeSide(enum.Enum):
    """Trade direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class StrategyType(enum.Enum):
    """Strategy identifier."""
    MEAN_REVERSION = "MEAN_REVERSION"
    TREND_SNIPER = "TREND_SNIPER"


class Trade(Base):
    """Trade record model."""
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    strategy_used = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    size = Column(Float, nullable=False)
    pnl_absolute = Column(Float, nullable=True)
    pnl_percent = Column(Float, nullable=True)
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)
    
    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, symbol={self.symbol}, side={self.side}, "
            f"strategy={self.strategy_used}, pnl={self.pnl_absolute})>"
        )


def get_engine():
    """Get or create SQLAlchemy engine (thread-safe singleton)."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                # Ensure data directory exists
                config.logging.database_path.parent.mkdir(parents=True, exist_ok=True)
                db_url = f"sqlite:///{config.logging.database_path}"
                _engine = create_engine(
                    db_url,
                    echo=False,
                    connect_args={"check_same_thread": False}
                )
                # Create tables
                Base.metadata.create_all(_engine)
    return _engine


def get_session_factory():
    """Get or create session factory (thread-safe singleton)."""
    global _SessionFactory
    if _SessionFactory is None:
        with _lock:
            if _SessionFactory is None:
                _SessionFactory = sessionmaker(bind=get_engine())
    return _SessionFactory


@contextmanager
def get_session() -> Session:
    """Get a database session with automatic commit/rollback."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_trade(
    symbol: str,
    strategy: StrategyType,
    side: TradeSide,
    entry_price: float,
    size: float
) -> Trade:
    """Create a new trade record."""
    with get_session() as session:
        trade = Trade(
            symbol=symbol,
            strategy_used=strategy.value,
            side=side.value,
            entry_price=entry_price,
            size=size,
            entry_time=datetime.now(timezone.utc)
        )
        session.add(trade)
        session.flush()
        trade_id = trade.id
    return get_trade_by_id(trade_id)


def close_trade(
    trade_id: int,
    exit_price: float
) -> Optional[Trade]:
    """Close an existing trade and calculate PnL."""
    with get_session() as session:
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if trade is None:
            return None
        
        trade.exit_price = exit_price
        trade.exit_time = datetime.now(timezone.utc)
        
        # Calculate PnL
        if trade.side == TradeSide.LONG.value:
            pnl_percent = (exit_price - trade.entry_price) / trade.entry_price
        else:  # SHORT
            pnl_percent = (trade.entry_price - exit_price) / trade.entry_price
        
        trade.pnl_percent = pnl_percent
        trade.pnl_absolute = pnl_percent * trade.entry_price * trade.size
        
    return get_trade_by_id(trade_id)


def get_trade_by_id(trade_id: int) -> Optional[Trade]:
    """Get a trade by ID."""
    with get_session() as session:
        trade = session.query(Trade).filter(Trade.id == trade_id).first()
        if trade:
            session.expunge(trade)
        return trade


def get_open_trades() -> list[Trade]:
    """Get all trades that haven't been closed."""
    with get_session() as session:
        trades = session.query(Trade).filter(Trade.exit_time.is_(None)).all()
        for trade in trades:
            session.expunge(trade)
        return trades


def get_open_trade_by_strategy(strategy: StrategyType) -> Optional[Trade]:
    """Get open trade for a specific strategy."""
    with get_session() as session:
        trade = session.query(Trade).filter(
            Trade.strategy_used == strategy.value,
            Trade.exit_time.is_(None)
        ).first()
        if trade:
            session.expunge(trade)
        return trade


def get_all_closed_trades() -> list[Trade]:
    """Get all closed trades for analysis."""
    with get_session() as session:
        trades = session.query(Trade).filter(
            Trade.exit_time.isnot(None)
        ).order_by(Trade.exit_time.desc()).all()
        for trade in trades:
            session.expunge(trade)
        return trades


def get_trades_by_strategy(strategy: StrategyType) -> list[Trade]:
    """Get all closed trades for a specific strategy."""
    with get_session() as session:
        trades = session.query(Trade).filter(
            Trade.strategy_used == strategy.value,
            Trade.exit_time.isnot(None)
        ).order_by(Trade.exit_time.desc()).all()
        for trade in trades:
            session.expunge(trade)
        return trades
