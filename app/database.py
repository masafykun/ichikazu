from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:////root/ichikazu/data/ichikazu.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """既存 short_urls テーブルへ新カラムを追加（ADD COLUMN IF NOT EXISTS が無いので個別try）。"""
    stmts = [
        "ALTER TABLE short_urls ADD COLUMN user_id INTEGER",
        "ALTER TABLE short_urls ADD COLUMN title VARCHAR(255)",
        "ALTER TABLE short_urls ADD COLUMN is_custom BOOLEAN DEFAULT 0 NOT NULL",
        "ALTER TABLE short_urls ADD COLUMN expires_at DATETIME",
    ]
    with engine.connect() as conn:
        for s in stmts:
            try:
                conn.execute(text(s))
                conn.commit()
            except Exception:
                conn.rollback()
