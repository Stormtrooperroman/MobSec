from sqlalchemy import (
    Column,
    String,
    DateTime,
    Integer,
    JSON,
    Enum,
    ForeignKey,
    Table,
    select,
)
from sqlalchemy.orm import declarative_base, relationship
import enum
from datetime import datetime, timezone

Base = declarative_base()


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


class Module(Base):
    __tablename__ = "modules"
    name = Column(String, nullable=False, primary_key=True)
    version = Column(String)
    description = Column(String)
    config = Column(JSON)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    chains = relationship("Chain", secondary=chain_modules, overlaps="modules")
    executions = relationship("ModuleExecution", back_populates="module")


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


async def get_chain_by_name(session, chain_name: str):
    return await session.execute(
        select(Chain).where(Chain.name == chain_name)
    ).scalar_one_or_none()


async def get_chain_execution_by_id(session, execution_id: str):
    return await session.execute(
        select(ChainExecution).where(ChainExecution.id == execution_id)
    ).scalar_one_or_none()


async def get_module_by_id(session, module_name: str):
    return await session.execute(
        select(Module).where(Module.name == module_name)
    ).scalar_one_or_none()
