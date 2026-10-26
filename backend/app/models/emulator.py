from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, func
from app.models.base import Base


class Emulator(Base):
    __tablename__ = "emulators"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    version = Column(String)
    description = Column(String)
    config = Column(JSON)
    status = Column(String, default="stopped")
    container_id = Column(String, nullable=True)
    ports = Column(JSON)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    active = Column(Boolean, default=True)
