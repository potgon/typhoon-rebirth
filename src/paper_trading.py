"""
Paper Trading Manager for the Hybrid Regime-Switching Trading Bot.
Tracks simulated balance and positions for paper trading.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass

from sqlalchemy import Column, Integer, Float, DateTime, String
from sqlalchemy.orm import Session

from src.database import Base, get_session, get_engine
from src.config import config

logger = logging.getLogger(__name__)


class PaperAccount(Base):
    """
    Paper trading account balance tracker.
    Stores the current simulated balance and tracks changes over time.
    """
    __tablename__ = "paper_account"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    balance = Column(Float, nullable=False)
    initial_balance = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class PaperPosition(Base):
    """
    Paper trading open position tracker.
    Stores currently open simulated positions.
    """
    __tablename__ = "paper_positions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # 'long' or 'short'
    size = Column(Float, nullable=False)  # Position size in base currency
    entry_price = Column(Float, nullable=False)
    margin_used = Column(Float, nullable=False)  # USDT locked for this position
    strategy = Column(String(30), nullable=False)
    opened_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


@dataclass
class SimulatedPosition:
    """Dataclass for position info."""
    id: int
    symbol: str
    side: str
    size: float
    entry_price: float
    margin_used: float
    strategy: str


class PaperTradingManager:
    """
    Manages paper trading account balance and positions.
    
    Features:
    - Persistent balance tracking in SQLite
    - Position margin accounting
    - PnL calculation on position close
    - Account reset capability
    """
    
    _instance = None
    
    def __new__(cls):
        """Singleton pattern to ensure one manager instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._ensure_tables()
        self._ensure_account()
    
    def _ensure_tables(self):
        """Create paper trading tables if they don't exist."""
        engine = get_engine()
        PaperAccount.__table__.create(engine, checkfirst=True)
        PaperPosition.__table__.create(engine, checkfirst=True)
    
    def _ensure_account(self):
        """Ensure a paper account exists, create if needed."""
        with get_session() as session:
            account = session.query(PaperAccount).first()
            if account is None:
                initial_balance = config.trading.simulated_balance
                if initial_balance <= 0:
                    initial_balance = 10000.0  # Default starting balance
                
                account = PaperAccount(
                    balance=initial_balance,
                    initial_balance=initial_balance,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc)
                )
                session.add(account)
                logger.info(f"Created paper trading account with {initial_balance} USDT")
    
    def get_balance(self) -> float:
        """Get current available balance (total - margin in use)."""
        with get_session() as session:
            account = session.query(PaperAccount).first()
            if account is None:
                return 0.0
            
            # Calculate margin in use
            margin_in_use = session.query(PaperPosition).with_entities(
                PaperPosition.margin_used
            ).all()
            total_margin = sum(m[0] for m in margin_in_use) if margin_in_use else 0.0
            
            return account.balance - total_margin
    
    def get_total_equity(self) -> float:
        """Get total account balance (without subtracting margin)."""
        with get_session() as session:
            account = session.query(PaperAccount).first()
            return account.balance if account else 0.0
    
    def get_initial_balance(self) -> float:
        """Get the initial starting balance."""
        with get_session() as session:
            account = session.query(PaperAccount).first()
            return account.initial_balance if account else 0.0
    
    def get_total_pnl(self) -> float:
        """Get total PnL since account creation."""
        initial = self.get_initial_balance()
        current = self.get_total_equity()
        return current - initial
    
    def get_pnl_percent(self) -> float:
        """Get PnL as percentage of initial balance."""
        initial = self.get_initial_balance()
        if initial <= 0:
            return 0.0
        return (self.get_total_pnl() / initial) * 100
    
    def open_position(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        strategy: str
    ) -> Optional[SimulatedPosition]:
        """
        Open a new paper position.
        
        Args:
            symbol: Trading pair
            side: 'long' or 'short'
            size: Position size in base currency
            entry_price: Entry price
            strategy: Strategy name
            
        Returns:
            SimulatedPosition if successful, None if insufficient balance
        """
        margin_required = size * entry_price
        available_balance = self.get_balance()
        
        if margin_required > available_balance:
            logger.warning(
                f"Insufficient balance for paper position. "
                f"Required: {margin_required:.2f}, Available: {available_balance:.2f}"
            )
            return None
        
        with get_session() as session:
            position = PaperPosition(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry_price,
                margin_used=margin_required,
                strategy=strategy,
                opened_at=datetime.now(timezone.utc)
            )
            session.add(position)
            session.flush()
            
            logger.info(
                f"Opened paper {side.upper()} position: {size} {symbol} @ {entry_price} "
                f"(Margin: {margin_required:.2f} USDT)"
            )
            
            return SimulatedPosition(
                id=position.id,
                symbol=position.symbol,
                side=position.side,
                size=position.size,
                entry_price=position.entry_price,
                margin_used=position.margin_used,
                strategy=position.strategy
            )
    
    def close_position(
        self,
        position_id: int,
        exit_price: float
    ) -> Optional[float]:
        """
        Close a paper position and realize PnL.
        
        Args:
            position_id: ID of the position to close
            exit_price: Exit price
            
        Returns:
            Realized PnL in USDT, or None if position not found
        """
        with get_session() as session:
            position = session.query(PaperPosition).filter(
                PaperPosition.id == position_id
            ).first()
            
            if position is None:
                logger.warning(f"Paper position {position_id} not found")
                return None
            
            # Calculate PnL
            if position.side == 'long':
                pnl = (exit_price - position.entry_price) * position.size
            else:  # short
                pnl = (position.entry_price - exit_price) * position.size
            
            # Update account balance
            account = session.query(PaperAccount).first()
            if account:
                account.balance += pnl
                account.updated_at = datetime.now(timezone.utc)
            
            # Remove position
            session.delete(position)
            
            logger.info(
                f"Closed paper {position.side.upper()} position: "
                f"{position.size} {position.symbol} @ {exit_price} "
                f"(PnL: {pnl:+.2f} USDT)"
            )
            
            return pnl
    
    def get_position_by_strategy(self, strategy: str) -> Optional[SimulatedPosition]:
        """Get open position for a specific strategy."""
        with get_session() as session:
            position = session.query(PaperPosition).filter(
                PaperPosition.strategy == strategy
            ).first()
            
            if position:
                return SimulatedPosition(
                    id=position.id,
                    symbol=position.symbol,
                    side=position.side,
                    size=position.size,
                    entry_price=position.entry_price,
                    margin_used=position.margin_used,
                    strategy=position.strategy
                )
            return None
    
    def get_all_positions(self) -> list[SimulatedPosition]:
        """Get all open paper positions."""
        with get_session() as session:
            positions = session.query(PaperPosition).all()
            return [
                SimulatedPosition(
                    id=p.id,
                    symbol=p.symbol,
                    side=p.side,
                    size=p.size,
                    entry_price=p.entry_price,
                    margin_used=p.margin_used,
                    strategy=p.strategy
                )
                for p in positions
            ]
    
    def reset_account(self, new_balance: float = None):
        """
        Reset the paper trading account.
        Closes all positions and resets balance to initial or specified amount.
        """
        with get_session() as session:
            # Delete all positions
            session.query(PaperPosition).delete()
            
            # Reset account balance
            account = session.query(PaperAccount).first()
            if account:
                new_initial = new_balance or config.trading.simulated_balance or 10000.0
                account.balance = new_initial
                account.initial_balance = new_initial
                account.created_at = datetime.now(timezone.utc)
                account.updated_at = datetime.now(timezone.utc)
        
        logger.info(f"Paper trading account reset to {new_initial} USDT")
    
    def get_account_summary(self) -> dict:
        """Get a summary of the paper trading account status."""
        return {
            "initial_balance": self.get_initial_balance(),
            "current_equity": self.get_total_equity(),
            "available_balance": self.get_balance(),
            "total_pnl": self.get_total_pnl(),
            "pnl_percent": self.get_pnl_percent(),
            "open_positions": len(self.get_all_positions())
        }


# Singleton instance
def get_paper_manager() -> PaperTradingManager:
    """Get the paper trading manager singleton."""
    return PaperTradingManager()
