from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, DateTime, Integer, JSON, Enum, select
import enum


Base = declarative_base()

class ScanStatus(enum.Enum):
    EMPTY = "N/A"
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"

class FileType(enum.Enum):
    APK = "apk"
    IPA = "ipa"
    ZIP = "zip"
    UNKNOWN = "unknown"

class FileModel(Base):
    __tablename__ = 'files'
    file_hash = Column(String, primary_key=True)
    original_name = Column(String)
    timestamp = Column(DateTime)
    size = Column(Integer)
    folder_path = Column(String)
    file_type = Column(Enum(FileType), nullable=False, default=FileType.UNKNOWN)
    
    # Scan information
    scan_status = Column(Enum(ScanStatus), default=ScanStatus.PENDING)
    scan_started_at = Column(DateTime, nullable=True)
    scan_completed_at = Column(DateTime, nullable=True)
    
    # Store detailed scan results as JSON
    scan_results = Column(JSON, nullable=True)
    
    # File hashes
    md5 = Column(String, nullable=True)
    sha1 = Column(String, nullable=True)
    sha256 = Column(String, nullable=True)