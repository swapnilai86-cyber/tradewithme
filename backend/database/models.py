from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer") # admin, trader, viewer
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    alert_preferences = relationship("AlertsPreference", back_populates="user", cascade="all, delete-orphan")
    paper_trades = relationship("PaperTrade", back_populates="user", cascade="all, delete-orphan")
    trade_history = relationship("TradeHistory", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol = Column(String, nullable=False)
    entry_price = Column(Float, nullable=True)
    exit_price = Column(Float, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watchlists")


class AlertsPreference(Base):
    __tablename__ = "alerts_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    alert_type = Column(String, nullable=False) # EARLY_RADAR, ENTRY_TRIGGER, EXITS, ERRORS
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="alert_preferences")


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symbol = Column(String, index=True, nullable=False)
    
    entry_price = Column(Float, nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    
    sl = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    qty = Column(Integer, nullable=False)
    
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    
    status = Column(String, index=True, default="OPEN") # OPEN, CLOSED
    hold_duration_mins = Column(Integer, nullable=True)
    exit_reason = Column(String, nullable=True) # TP_HIT, SL_HIT, TIME_EXIT, MANUAL
    
    visible_to = Column(JSONB, nullable=True) # Array of user_ids who can view
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="paper_trades")
    history = relationship("TradeHistory", back_populates="paper_trade", cascade="all, delete-orphan")

    @property
    def days_held(self) -> Optional[float]:
        if self.hold_duration_mins is not None:
            return round(self.hold_duration_mins / (60 * 24), 2)
        return None


class TradeHistory(Base):
    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    paper_trades_id = Column(Integer, ForeignKey("paper_trades.id", ondelete="CASCADE"), index=True, nullable=False)
    action = Column(String, nullable=False) # CREATE, UPDATE, CLOSE
    details = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="trade_history")
    paper_trade = relationship("PaperTrade", back_populates="history")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    action = Column(String, nullable=False) # LOGIN, CONFIG_CHANGE, ADMIN_ACTION
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    details = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="audit_logs")


class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True, nullable=False)
    token = Column(String, nullable=False) # m.Stock token
    exchange = Column(String, default="NSE")
    sector = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DailyScannerOutput(Base):
    __tablename__ = "daily_scanner_output"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(String, index=True, nullable=False)
    signal_type = Column(String, nullable=False) # EARLY_RADAR, ENTRY_TRIGGER, RETEST_REENTRY
    rsi = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class SystemAlert(Base):
    __tablename__ = "system_alerts"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, nullable=False)
    alert_type = Column(String, index=True, nullable=False) # EARLY_RADAR, ENTRY_TRIGGER, EXITS, ERRORS
    price = Column(Float, nullable=True)
    message = Column(String, nullable=False)
    data = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
