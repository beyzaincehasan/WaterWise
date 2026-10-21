"""WaterWise Backend - Veritabanı Bağlantı ve Oturum Yönetimi.

SQLAlchemy ile SQLite veya PostgreSQL bağlantısını sağlar.
"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.app.config import settings

# SQLite için thread güvenliği ayarı:
# SQLite varsayılan olarak bağlantının aynı thread'de kullanılmasını ister.
# FastAPI eşzamanlı isteklerinde hata almamak için check_same_thread=False yapılır.
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
    pool_pre_ping=True,  # PostgreSQL kopan bağlantıları yeniden denemek için
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator:
    """FastAPI Depends mekanizması için veritabanı oturumu sağlayıcısı."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tüm modellerin tablolarını veritabanında oluşturur."""
    import backend.app.models  # Modelleri Base metadata'sına kaydetmek için içe aktar
    Base.metadata.create_all(bind=engine)

