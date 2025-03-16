from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from fastapi import UploadFile
import hashlib
import os
import aiofiles
from datetime import datetime
from typing import Optional, List, Dict, Any
import zipfile
from app.models.app import FileModel, ScanStatus, FileType, Base
import logging
import shutil
from app.core.settings_db import AsyncSessionLocal
from app.models.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class AsyncStorageService:
    def __init__(self, storage_dir: str = "/shared_data"):
        self.storage_dir = storage_dir
        database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:password@db:5432/mobsec_db')
        self.engine = create_async_engine(database_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def init_db(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def determine_file_type(self, file_path: str) -> FileType:
        """
        Determine if the file is an APK, IPA, or ZIP
        """
        try:
            # Check if it's a zip file first
            if zipfile.is_zipfile(file_path):
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    file_list = zip_ref.namelist()
                    
                    # Check for APK specific files
                    if any(name.startswith('AndroidManifest.xml') or 
                          name.startswith('classes.dex') for name in file_list):
                        return FileType.APK
                    
                    # Check for IPA specific files/directories
                    if any(name.startswith('Payload/') and 
                          name.endswith('.app/') for name in file_list):
                        return FileType.IPA
                    
                    # If it's a zip but not APK or IPA, it's a ZIP
                    return FileType.ZIP
                    
        except Exception as e:
            print(f"Error determining file type: {e}")
            
        return FileType.UNKNOWN

    def _get_folder_structure(self, filename: str, file_hash: str) -> str:
        """Generate a folder name based on the original filename and hash"""
        return "_".join(filename.split('.')[0].split()) + '-' + file_hash

    def _get_file_path(self, original_name: str, file_hash: str, folder: str) -> str:
        """Generate the full file path using original name, hash, and folder"""
        return os.path.join(self.storage_dir, folder, original_name)

    async def get_auto_run_settings(self) -> Dict[str, Any]:
        """Get auto-run settings from database"""
        async with AsyncSessionLocal() as db:
            query = select(Settings)
            result = await db.execute(query)
            settings = result.scalar_one_or_none()
            
            if not settings:
                return {
                    "zip_action": None,
                    "zip_action_type": None,
                    "apk_action": None,
                    "apk_action_type": None,
                    "ipa_action": None,
                    "ipa_action_type": None
                }
            return settings.to_dict()

    async def handle_uploaded_file(self, content: UploadFile) -> str:
        """Handle file upload and process based on file type"""
        # Ensure base storage directory exists
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # Calculate multiple hashes while saving the file
        md5 = hashlib.md5()
        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        file_size = 0
        
        temp_path = os.path.join(self.storage_dir, f"temp_{content.filename}")
        
        async with aiofiles.open(temp_path, "wb") as destination:
            while chunk := await content.read(8192):
                md5.update(chunk)
                sha1.update(chunk)
                sha256.update(chunk)
                file_size += len(chunk)
                await destination.write(chunk)
        
        file_hash = md5.hexdigest()
        folder = self._get_folder_structure(content.filename, file_hash)
        folder_path = os.path.join(self.storage_dir, folder)
        os.makedirs(folder_path, exist_ok=True)
        
        final_path = self._get_file_path(content.filename, file_hash, folder)
        os.rename(temp_path, final_path)
        
        # Determine file type
        file_type = self.determine_file_type(final_path)
        
        # If file is a ZIP, extract it to source_code folder
        if file_type == FileType.ZIP:
            source_code_path = os.path.join(folder_path, "source_code")
            os.makedirs(source_code_path, exist_ok=True)
            try:
                with zipfile.ZipFile(final_path, 'r') as zip_ref:
                    zip_ref.extractall(source_code_path)
                logger.info(f"Successfully extracted ZIP file to {source_code_path}")
            except Exception as e:
                logger.error(f"Error extracting ZIP file: {str(e)}")
        
        file_model = FileModel(
            file_hash=file_hash,
            original_name=content.filename,
            timestamp=datetime.now(),
            size=file_size,
            folder_path=folder,
            file_type=file_type,
            scan_status=ScanStatus.EMPTY,
            md5=md5.hexdigest(),
            sha1=sha1.hexdigest(),
            sha256=sha256.hexdigest()
        )
        
        async with self.async_session() as session:
            existing = await session.get(FileModel, file_hash)
            if not existing:
                session.add(file_model)
                await session.commit()

        # Check auto-run settings and start analysis if configured
        try:
            settings = await self.get_auto_run_settings()
            
            action = None
            action_type = None
            
            if file_type == FileType.APK:
                action = settings['apk_action']
                action_type = settings['apk_action_type']
            elif file_type == FileType.IPA:
                action = settings['ipa_action']
                action_type = settings['ipa_action_type']
            elif file_type == FileType.ZIP:
                action = settings['zip_action']
                action_type = settings['zip_action_type']
            
            if action and action_type:
                await self.update_scan_status(file_hash, ScanStatus.SCANNING)
                
                if action_type == 'module':
                    from app.modules.module_manager import ModuleManager
                    module_manager = ModuleManager(
                        redis_url=os.getenv('REDIS_URL'),
                        modules_path=os.getenv('MODULES_PATH')
                    )
                    await module_manager.run_module(action, file_hash)
                elif action_type == 'chain':
                    from app.modules.chain_manager import  ChainManager
                    chain_manager = ChainManager()
                    await chain_manager.run_chain(action, file_hash)
                
                logger.info(f"Auto-run {action_type} '{action}' started for file {file_hash}")
        except Exception as e:
            logger.error(f"Error in auto-run processing: {str(e)}")
        
        return file_hash

    async def update_scan_status(self, file_hash: str, status: ScanStatus, results: dict = None) -> bool:
        """Update the scan status and results for a file"""
        async with self.async_session() as session:
            file_model = await session.get(FileModel, file_hash)
            if not file_model:
                return False
            
            file_model.scan_status = status
            
            if status == ScanStatus.SCANNING:
                file_model.scan_started_at = datetime.now()
            elif status in (ScanStatus.COMPLETED, ScanStatus.FAILED):
                file_model.scan_completed_at = datetime.now()
            
            if results:
                file_model.scan_results = results
            
            await session.commit()
            return True

    async def get_scan_status(self, file_hash: str) -> Optional[dict]:
        """Get the current scan status and results for a file"""
        async with self.async_session() as session:
            file_model = await session.get(FileModel, file_hash)
            if not file_model:
                return None
            
            return {
                    'file_hash': file_model.file_hash,
                    'original_name': file_model.original_name,
                    'timestamp': file_model.timestamp,
                    'size': file_model.size,
                    'file_type': file_model.file_type.value,
                    'scan_status': file_model.scan_status.value,
                    'scan_started_at': file_model.scan_started_at,
                    'scan_completed_at': file_model.scan_completed_at,
                    'scan_results': file_model.scan_results,
                    'hashes': {
                        'md5': file_model.md5,
                        'sha1': file_model.sha1,
                        'sha256': file_model.sha256
                    }
                }

    async def list_files(self, skip: int = 0, limit: int = 10) -> List[dict]:
        """
        List all files with pagination support.
        Returns a list of file metadata dictionaries.
        """
        async with self.async_session() as session:
            # Create query with pagination
            query = select(FileModel).offset(skip).limit(limit).order_by(FileModel.timestamp.desc())
            
            # Execute query
            result = await session.execute(query)
            files = result.scalars().all()
            
            # Convert to list of dictionaries
            file_list = []
            for file in files:
                file_list.append({
                    'file_hash': file.file_hash,
                    'original_name': file.original_name,
                    'timestamp': file.timestamp,
                    'size': file.size,
                    'file_type': file.file_type.value,
                    'scan_status': file.scan_status.value,
                    'scan_started_at': file.scan_started_at,
                    'scan_completed_at': file.scan_completed_at,
                    'hashes': {
                        'md5': file.md5,
                        'sha1': file.sha1,
                        'sha256': file.sha256
                    }
                })
            
            return file_list

    async def get_total_files(self) -> int:
        """
        Get total number of files in the database.
        """
        async with self.async_session() as session:
            query = select(FileModel)
            result = await session.execute(query)
            return len(result.scalars().all())

    async def delete_file(self, file_hash: str) -> bool:
        """
        Delete a file and its associated data from both database and storage.
        
        Args:
            file_hash (str): The hash of the file to delete
            
        Returns:
            bool: True if deletion was successful, False otherwise
        """
        try:
            # First get the file info from database to know the folder path
            async with self.async_session() as session:
                file_model = await session.get(FileModel, file_hash)
                if not file_model:
                    return False
                
                folder_path = os.path.join(self.storage_dir, file_model.folder_path)
                # Delete from database first
                await session.delete(file_model)
                await session.commit()
                
                # Then delete the folder and its contents from storage
                if os.path.exists(folder_path):
                    try:
                        shutil.rmtree(folder_path)
                    except Exception as e:
                        logger.error(f"Error removing directory {folder_path}: {str(e)}")
                        raise
                
                return True
            
        except Exception as e:
            print(f"Error deleting file {file_hash}: {e}")
            return False


storage = AsyncStorageService()

async def setup():
    await storage.init_db()