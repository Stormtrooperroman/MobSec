import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    select,
)
from sqlalchemy.orm import relationship
from app.models.base import Base


class ChainStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


chain_modules = Table(
    "chain_modules",
    Base.metadata,
    Column("chain_name", String, ForeignKey("chains.name")),
    Column("module_name", String, ForeignKey("modules.name")),
    Column("order", Integer),
    Column("parameters", JSON),
)


class Chain(Base):
    __tablename__ = "chains"

    name = Column(String, primary_key=True)
    description = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    modules = relationship(
        "Module", secondary=chain_modules, order_by="chain_modules.c.order"
    )
    executions = relationship("ChainExecution", back_populates="chain")


class ChainExecution(Base):
    __tablename__ = "chain_executions"

    id = Column(String, primary_key=True)
    chain_name = Column(String, ForeignKey("chains.name"))
    status = Column(Enum(ChainStatus), default=ChainStatus.PENDING)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)

    # Relationships
    chain = relationship("Chain", back_populates="executions")
    module_executions = relationship(
        "ModuleExecution", back_populates="chain_execution"
    )


class ModuleExecution(Base):
    __tablename__ = "module_executions"

    id = Column(String, primary_key=True)
    chain_execution_id = Column(String, ForeignKey("chain_executions.id"))
    module_name = Column(String, ForeignKey("modules.name"))
    order = Column(Integer)
    status = Column(Enum(ChainStatus), default=ChainStatus.PENDING)
    started_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    parameters = Column(JSON)
    results = Column(JSON, nullable=True)
    error_message = Column(String, nullable=True)

    chain_execution = relationship("ChainExecution", back_populates="module_executions")
    module = relationship("Module", back_populates="executions")
