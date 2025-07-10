from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


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
