import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from app.core.database_manager import db_manager
from app.models.frida_script import FridaScript

logger = logging.getLogger(__name__)


class FridaScriptService:
    def __init__(self):
        self.scripts_dir = os.getenv("FRIDA_SCRIPTS_DIR", "/shared_data/frida_scripts")
        self._ensure_scripts_directory()
        self._setup_database()

    def _ensure_scripts_directory(self):
        """Creates scripts directory if it doesn't exist"""
        try:
            os.makedirs(self.scripts_dir, exist_ok=True)
            logger.info("Scripts directory ensured: %s", self.scripts_dir)
        except Exception as e:
            logger.error("Error creating scripts directory: %s", str(e))
            raise

    def _setup_database(self):
        """Setup database connection"""
        try:
            self.async_session = db_manager.session_factory
            logger.info("Database connection established for FridaScriptService")
        except Exception as e:
            logger.error("Error setting up database: %s", str(e))
            raise

    async def create_script(self, name: str, content: str) -> Dict[str, Any]:
        """Creates a new script and saves it to file system and database"""
        try:
            if await self.get_script_by_name(name):
                raise ValueError(f"Script with name '{name}' already exists")

            safe_filename = self._create_safe_filename(name)
            file_path = os.path.join(self.scripts_dir, safe_filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            async with self.async_session() as session:
                script = FridaScript(
                    name=name,
                    file_path=file_path,
                )
                session.add(script)
                await session.commit()
                await session.refresh(script)

            logger.info("Script '%s' created successfully", name)
            return {
                "id": script.id,
                "name": script.name,
                "file_path": script.file_path,
                "created_at": script.created_at.isoformat(),
                "updated_at": script.updated_at.isoformat(),
            }

        except Exception as e:
            logger.error("Error creating script '%s': %s", name, str(e))
            if "file_path" in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            raise

    async def get_script_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Gets script by name"""
        try:
            async with self.async_session() as session:
                query = select(FridaScript).where(FridaScript.name == name)
                result = await session.execute(query)
                script = result.scalar_one_or_none()

                if script:
                    return {
                        "id": script.id,
                        "name": script.name,
                        "file_path": script.file_path,
                        "created_at": script.created_at.isoformat(),
                        "updated_at": script.updated_at.isoformat(),
                    }
                return None
        except Exception as e:
            logger.error("Error getting script '%s': %s", name, str(e))
            return None

    async def get_script_content(self, name: str) -> Optional[str]:
        """Gets script content by name"""
        try:
            script_info = await self.get_script_by_name(name)
            if not script_info:
                return None

            file_path = script_info["file_path"]
            if not os.path.exists(file_path):
                logger.error("Script file not found: %s", file_path)
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

        except Exception as e:
            logger.error("Error getting script content for '%s': %s", name, str(e))
            return None

    async def update_script(
        self, name: str, content: str = None
    ) -> Optional[Dict[str, Any]]:
        """Updates script"""
        try:
            async with self.async_session() as session:
                query = select(FridaScript).where(FridaScript.name == name)
                result = await session.execute(query)
                script = result.scalar_one_or_none()

                if not script:
                    raise ValueError(f"Script '{name}' not found")

                if content is not None:
                    with open(script.file_path, "w", encoding="utf-8") as f:
                        f.write(content)

                script.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(script)

            logger.info("Script '%s' updated successfully", name)
            return await self.get_script_by_name(name)

        except Exception as e:
            logger.error("Error updating script '%s': %s", name, str(e))
            raise

    async def delete_script(self, name: str) -> bool:
        """Deletes script"""
        try:
            async with self.async_session() as session:
                query = select(FridaScript).where(FridaScript.name == name)
                result = await session.execute(query)
                script = result.scalar_one_or_none()

                if not script:
                    raise ValueError(f"Script '{name}' not found")

                if os.path.exists(script.file_path):
                    os.remove(script.file_path)

                await session.delete(script)
                await session.commit()

            logger.info("Script '%s' deleted successfully", name)
            return True

        except Exception as e:
            logger.error("Error deleting script '%s': %s", name, str(e))
            raise

    async def list_scripts(self) -> List[Dict[str, Any]]:
        """Gets list of all scripts"""
        try:
            async with self.async_session() as session:
                query = select(FridaScript).order_by(FridaScript.created_at.desc())
                result = await session.execute(query)
                scripts = result.scalars().all()

                return [
                    {
                        "id": script.id,
                        "name": script.name,
                        "file_path": script.file_path,
                        "created_at": script.created_at.isoformat(),
                        "updated_at": script.updated_at.isoformat(),
                    }
                    for script in scripts
                ]
        except Exception as e:
            logger.error("Error listing scripts: %s", str(e))
            return []

    def _create_safe_filename(self, name: str) -> str:
        """Creates safe filename from script name"""
        safe_name = re.sub(r"[^\w\-_.]", "_", name)
        return f"{safe_name}.js"

    async def script_exists(self, name: str) -> bool:
        """Checks if script with given name exists"""
        return await self.get_script_by_name(name) is not None

    async def get_script_stats(self) -> Dict[str, Any]:
        """Gets script statistics"""
        try:
            async with self.async_session() as session:
                total_query = select(FridaScript)
                total_result = await session.execute(total_query)
                total_scripts = len(total_result.scalars().all())

                today_start = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                recent_query = select(FridaScript).where(
                    FridaScript.created_at >= today_start
                )
                recent_result = await session.execute(recent_query)
                recent_scripts = len(recent_result.scalars().all())

                return {
                    "total_scripts": total_scripts,
                    "scripts_today": recent_scripts,
                    "scripts_directory": self.scripts_dir,
                }
        except Exception as e:
            logger.error("Error getting script stats: %s", str(e))
            return {
                "total_scripts": 0,
                "scripts_today": 0,
                "scripts_directory": self.scripts_dir,
            }
