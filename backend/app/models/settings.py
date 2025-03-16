from sqlalchemy import Column, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"

    id = Column(String, primary_key=True, default="global")
    zip_action = Column(String, nullable=True)
    zip_action_type = Column(String, nullable=True)
    apk_action = Column(String, nullable=True)
    apk_action_type = Column(String, nullable=True)
    ipa_action = Column(String, nullable=True)
    ipa_action_type = Column(String, nullable=True)

    def to_dict(self):
        return {
            "zip_action": self.zip_action,
            "zip_action_type": self.zip_action_type,
            "apk_action": self.apk_action,
            "apk_action_type": self.apk_action_type,
            "ipa_action": self.ipa_action,
            "ipa_action_type": self.ipa_action_type
        } 