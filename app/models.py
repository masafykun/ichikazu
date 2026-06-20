from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    plan = Column(String(16), default="free", nullable=False)  # free / pro
    stripe_customer_id = Column(String(64), nullable=True)
    stripe_subscription_id = Column(String(64), nullable=True)
    api_key = Column(String(64), unique=True, index=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    urls = relationship("ShortURL", back_populates="user")


class ShortURL(Base):
    __tablename__ = "short_urls"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, index=True, nullable=False)
    original_url = Column(String(2048), nullable=False)
    creator_ip = Column(String(64), nullable=True)
    creator_ua = Column(String(512), nullable=True)
    click_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

    # 有料化で追加（アカウント・Pro機能）
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    is_custom = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="urls")
    access_logs = relationship("AccessLog", back_populates="short_url", cascade="all, delete-orphan")


class AccessLog(Base):
    __tablename__ = "access_logs"

    id = Column(Integer, primary_key=True, index=True)
    short_url_id = Column(Integer, ForeignKey("short_urls.id"), nullable=False, index=True)
    accessed_at = Column(DateTime, server_default=func.now(), nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    referer = Column(String(2048), nullable=True)

    short_url = relationship("ShortURL", back_populates="access_logs")


class StripeEvent(Base):
    __tablename__ = "stripe_events"

    id = Column(String(64), primary_key=True)
    type = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
