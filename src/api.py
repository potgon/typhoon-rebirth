"""
Read-only API for the Trading Bot Dashboard.
Serves status, positions, and trade history from SQLite.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os

from src.database import (
    get_session, 
    Trade, 
    get_open_trades, 
    get_all_closed_trades, 
    PaperAccount,
    PaperPosition
)
from src.watchman import Watchman, MarketRegime
from src.exchange_client import ExchangeClient
from src.config import config
from src.paper_trading import get_paper_manager

app = FastAPI(title="Typhoon Rebirth Dashboard")

# --- Models ---

class TradeSchema(BaseModel):
    id: int
    symbol: str
    strategy_used: str
    side: str
    entry_price: float
    exit_price: Optional[float]
    size: float
    pnl_absolute: Optional[float]
    pnl_percent: Optional[float]
    entry_time: datetime
    exit_time: Optional[datetime]

class PositionSchema(BaseModel):
    symbol: str
    side: str
    size: float
    entry_price: float
    current_pnl: float
    strategy: str

class StatusSchema(BaseModel):
    regime: str
    balance: float
    equity: float
    active_strategies: List[str]
    cooldown: bool

# --- Routes ---

@app.get("/api/status", response_model=StatusSchema)
async def get_status():
    """Get current bot status."""
    # 1. Get Regime (We need to instantiate Watchman briefly or share state? 
    # For simplicity in this read-only API, we might rely on logs or 
    # re-calculate if possible, but simplest is to check open positions 
    # or just assume specific state. 
    # Ideally, the bot would write its state to DB/File. 
    # For now, let's return what we can from DB/Config)
    
    # Since Main loop runs separately, we can't easily access the *live* Watchman instance
    # without an IPC mechanism. 
    # Workaround: For this v1, we focus on Balance & Positions which ARE in DB.
    # Regime might be 'Unknown' for API unless we persist it.
    
    regime = "Tracking..." # Placeholder as we don't persist regime yet
    
    # Balance
    balance = 0.0
    equity = 0.0
    
    if config.trading.dry_run and config.trading.simulated_balance > 0:
        pm = get_paper_manager()
        balance = pm.get_balance()
        equity = pm.get_total_equity()
    else:
        # Live/Dry without sim balance - try to fetch from exchange
        try:
            client = ExchangeClient()
            balance = client.get_balance("USDT")
            equity = balance # Approx
        except Exception:
            balance = 0.0
            equity = 0.0

    return {
        "regime": regime,
        "balance": balance,
        "equity": equity,
        "active_strategies": [], # To be implemented
        "cooldown": False
    }

@app.get("/api/trades", response_model=List[TradeSchema])
async def get_trades():
    """Get recent closed trades."""
    trades = get_all_closed_trades()
    return trades[:50] # Limit to last 50

@app.get("/api/positions", response_model=List[PositionSchema])
async def get_positions():
    """Get currently open positions."""
    positions = []
    
    if config.trading.dry_run and config.trading.simulated_balance > 0:
        # Get paper positions
        with get_session() as session:
            paper_pos = session.query(PaperPosition).all()
            for p in paper_pos:
                # Calculate simple PnL estimate
                # Note: We don't have real-time price here easily without fetching
                # For v1, we might send 0 or try to fetch if performance allows
                current_pnl = 0.0 
                
                positions.append({
                    "symbol": p.symbol,
                    "side": p.side,
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "current_pnl": current_pnl,
                    "strategy": p.strategy
                })
    else:
        # Real positions from DB 'trades' table that are open
        open_trades = get_open_trades()
        for t in open_trades:
            positions.append({
                "symbol": t.symbol,
                "side": t.side,
                "size": t.size,
                "entry_price": t.entry_price,
                "current_pnl": 0.0,
                "strategy": t.strategy_used
            })
            
    return positions

# --- Static Files ---

# Create dashboard directory if not exists
os.makedirs("src/dashboard", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="src/dashboard"), name="static")

@app.get("/")
async def read_root():
    return FileResponse("src/dashboard/index.html")
