from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLEnum, JSON, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ModuleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ExternalModule(Base):
    """SQLAlchemy model for database storage of external modules"""

    __tablename__ = "external_modules"

    module_id = Column(String, primary_key=True)
    base_url = Column(String, nullable=False)
    config = Column(JSON, nullable=False)
    healthcheck_url = Column(String, nullable=True)
    registered_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_heartbeat = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    status = Column(SQLEnum(ModuleStatus), default=ModuleStatus.ACTIVE)
    error_message = Column(String, nullable=True)

    def to_dict(self) -> dict:
        """Convert SQLAlchemy model to dictionary"""
        module_dict = {
            "module_id": self.module_id,
            "base_url": self.base_url,
            "config": self.config,
            "healthcheck_url": self.healthcheck_url,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "status": self.status,
            "error_message": self.error_message,
        }

        # Add UI component information if available
        if self.config and self.config.get("has_custom_ui"):
            module_dict["has_custom_ui"] = True
            module_dict["ui_component"] = self.config.get("ui_component", {})
        else:
            module_dict["has_custom_ui"] = False

        return module_dict

    @classmethod
    def from_dict(cls, data: dict) -> "ExternalModule":
        """Create SQLAlchemy model from dictionary"""
        return cls(
            module_id=data["module_id"],
            base_url=data["base_url"],
            config=data["config"],
            healthcheck_url=data.get("healthcheck_url"),
            registered_at=data.get("registered_at", datetime.now(timezone.utc)),
            last_heartbeat=data.get("last_heartbeat", datetime.now(timezone.utc)),
            status=data.get("status", ModuleStatus.ACTIVE),
            error_message=data.get("error_message"),
        )
