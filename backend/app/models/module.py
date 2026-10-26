import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, JSON, String
from sqlalchemy.orm import relationship
from app.models.base import Base


class ModuleType(str, enum.Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class ModuleSource(str, enum.Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class ModuleStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class Module(Base):
    __tablename__ = "modules"

    name = Column(String, nullable=False, primary_key=True)
    version = Column(String, nullable=True)
    description = Column(String, nullable=True)
    config = Column(JSON, nullable=True)
    module_type = Column(Enum(ModuleType), default=ModuleType.STATIC)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    source = Column(Enum(ModuleSource), default=ModuleSource.INTERNAL, nullable=False)

    base_url = Column(String, nullable=True, default=None)
    healthcheck_url = Column(String, nullable=True, default=None)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True, default=None)
    status = Column(Enum(ModuleStatus), nullable=True, default=None)
    error_message = Column(String, nullable=True, default=None)

    chains = relationship("Chain", secondary="chain_modules", overlaps="modules")
    executions = relationship("ModuleExecution", back_populates="module")

    def to_dict(self) -> dict:
        module_dict = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "config": self.config,
            "module_type": self.module_type,
            "source": self.source,
            "base_url": self.base_url,
            "healthcheck_url": self.healthcheck_url,
            "registered_at": self.created_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
            "error_message": self.error_message,
        }

        if self.config and self.config.get("has_custom_ui"):
            module_dict["has_custom_ui"] = True
            module_dict["ui_component"] = self.config.get("ui_component", {})
        else:
            module_dict["has_custom_ui"] = False

        return module_dict

    @classmethod
    def from_dict(cls, data: dict) -> "Module":
        return cls(
            name=data.get("name") or data.get("module_id"),
            version=data.get("version"),
            description=data.get("description"),
            config=data.get("config"),
            module_type=data.get("module_type", ModuleType.STATIC),
            source=data.get("source", ModuleSource.INTERNAL),
            base_url=data.get("base_url"),
            healthcheck_url=data.get("healthcheck_url"),
            created_at=data.get("registered_at", datetime.now(timezone.utc)),
            last_heartbeat=data.get("last_heartbeat"),
            status=data.get("status"),
            error_message=data.get("error_message"),
        )
