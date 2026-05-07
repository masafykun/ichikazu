from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from .database import Base


class ShortURL(Base):
    __tablename__ = "short_urls"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(16), unique=True, index=True, nullable=False)
    original_url = Column(String(2048), nullable=False)
    creator_ip = Column(String(64), nullable=True)
    creator_ua = Column(String(512), nullable=True)
    click_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_accessed_at = Column(DateTime, nullable=True)

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
