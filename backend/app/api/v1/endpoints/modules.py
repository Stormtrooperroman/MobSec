from fastapi import APIRouter, HTTPException, status, Body
from typing import Dict, List, Any
import logging
from app.modules.module_manager import ModuleManager
import os
import docker
from app.core.app_manager import storage
import httpx
from app.modules.external_module_registry import module_registry
from app.models.external_module import ModuleStatus
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

router = APIRouter()

module_manager = ModuleManager(
    redis_url=os.getenv("REDIS_URL"), modules_path=os.getenv("MODULES_PATH")
)


@router.get("/")
async def list_modules() -> List[Dict]:
    """
    Get information and status of all available internal modules.

    Returns:
    - List[dict]: A list of dictionaries, each containing:
        - id (str): The unique identifier of the module
        - name (str): The display name of the module
        - description (str): Module description or 'No description available'
        - active (bool): Current running status of the module's container

    Raises:
    - 500: If there is an error retrieving the module list or status
    """
    try:
        modules_info = []
        docker_client = docker.from_env()

        modules = [
            d
            for d in os.listdir(module_manager.modules_path)
            if os.path.isdir(os.path.join(module_manager.modules_path, d))
        ]

        for module_name in modules:
            container_name = f"mobsec_{module_name}"

            module_config = module_manager.modules_config.get(module_name, {})

            module_info = {
                "id": module_config.get("id", module_name),
                "name": module_config.get("display_name", module_name),
                "description": module_config.get(
                    "description", "No description available"
                ),
                "active": False,
                "is_external": False,
                "version": module_config.get("version", "0.1"),
                "input_formats": module_config.get("input_formats", ["apk"]),
            }

            try:
                container = docker_client.containers.get(container_name)
                module_info["active"] = container.status == "running"
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.error(
                    f"Error checking container status for {module_name}: {str(e)}"
                )

            modules_info.append(module_info)

        return modules_info

    except Exception as e:
        logger.error(f"Error listing modules: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing modules: {str(e)}",
        )


@router.get("/all")
async def list_all_modules() -> List[Dict]:
    """
    Get information and status of all available modules (internal and external).

    Returns:
    - List[dict]: A list of dictionaries containing both internal and external modules
    """
    try:
        internal_modules = await list_modules()

        external_modules = await module_registry.list_modules()

        external_modules_formatted = [
            {
                "id": module["module_id"],
                "name": module["config"]["name"],
                "description": module["config"].get(
                    "description", "No description available"
                ),
                "active": module["status"] == ModuleStatus.ACTIVE,
                "is_external": True,
                "version": module["config"].get("version"),
                "input_formats": module["config"].get("input_formats", []),
            }
            for module in external_modules
        ]

        return internal_modules + external_modules_formatted

    except Exception as e:
        logger.error(f"Error listing all modules: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing all modules: {str(e)}",
        )


@router.post("/{module_id}/toggle")
async def toggle_module(module_id: str) -> Dict:
    """
    Toggle a module's active state (start/stop).

    Parameters:
    - module_id (str): The unique identifier of the module to toggle

    Returns:
    - dict: A dictionary containing:
        - status (str): 'success' if the operation was successful
        - message (str): A description of what was done
        - active (bool): The new state of the module (True if activated, False if deactivated)

    Raises:
    - 404: If the module with the given ID is not found
    - 500: If there is an error during the toggle operation
    """
    try:
        module_name = None
        for name, config in module_manager.modules_config.items():
            if str(config.get("id", name)) == module_id:
                module_name = name
                break

        if not module_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with ID {module_id} not found",
            )

        container_name = f"mobsec_{module_name}"
        try:
            container = module_manager.docker_client.containers.get(container_name)
            if container.status == "running":
                await module_manager.stop_module(module_name)
                return {
                    "status": "success",
                    "message": f"Module {module_name} deactivated",
                    "active": False,
                }
            else:
                await module_manager.start_module(module_name)
                return {
                    "status": "success",
                    "message": f"Module {module_name} activated",
                    "active": True,
                }
        except docker.errors.NotFound:
            logger.info(f"No existing container found with name: {container_name}")
            await module_manager.start_module(module_name)
            return {
                "status": "success",
                "message": f"Module {module_name} activated",
                "active": True,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling module: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling module: {str(e)}",
        )


@router.post("/{module_id}/rebuild")
async def rebuild_module(module_id: str) -> Dict:
    """
    Rebuild and restart a specific module.

    Parameters:
    - module_id (str): The unique identifier of the module to rebuild

    Returns:
    - dict: A dictionary containing:
        - status (str): 'success' if the operation was successful
        - message (str): A description of what was done
        - active (bool): The new state of the module (always True after rebuild)

    Raises:
    - 404: If the module with the given ID is not found
    - 500: If there is an error during the rebuild operation
    """
    try:
        module_name = None
        for name, config in module_manager.modules_config.items():
            if str(config.get("id", name)) == module_id:
                module_name = name
                break

        if not module_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with ID {module_id} not found",
            )

        # Stop the module if it's running
        await module_manager.stop_module(module_name)

        # Start the module (this will rebuild the image and start a new container)
        await module_manager.start_module(module_name)

        return {
            "status": "success",
            "message": f"Module {module_name} has been rebuilt and restarted",
            "active": True,
        }

    except Exception as e:
        logger.error(f"Error rebuilding module: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rebuilding module: {str(e)}",
        )


@router.post("/{module_name}/run")
async def run_module(module_name: str, request: Dict[str, Any] = Body(...)):
    """
    Run a specific module (internal or external) on a file.

    Parameters:
    - module_name (str): Name or ID of the module to run
    - request (Dict[str, Any]): Request body containing:
        - file_hash (str): Hash of the file to analyze

    Returns:
    - dict: A dictionary containing:
        - status (str): 'success' if the task was submitted
        - message (str): Description of the action taken
        - task_id (str): Unique identifier for tracking the task

    Raises:
    - 404: If the module or file is not found
    - 422: If file_hash is missing from request body
    - 500: If there is an error submitting the task
    """
    try:
        file_hash = request.get("file_hash")
        if not file_hash:
            raise HTTPException(
                status_code=422, detail="file_hash is required in request body"
            )

        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(
                status_code=404, detail=f"File with hash '{file_hash}' not found"
            )

        folder = file_info.get("folder_path", "")
        if not folder:
            original_name = file_info.get("original_name", "unknown")
            folder = "_".join(original_name.split(".")[0].split()) + "-" + file_hash

        data = {
            "folder_path": folder,
            "file_name": file_info.get("original_name", ""),
            "file_type": file_info.get("file_type", "unknown"),
        }

        task_id = await module_manager.submit_task(module_name, data, file_hash)

        if not task_id:
            raise HTTPException(status_code=500, detail="Failed to create task")

        return {
            "status": "success",
            "message": f"{module_name} task submitted for file {file_hash}",
            "task_id": task_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting {module_name} task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")


def discover_module_ui_components() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically discover module UI components across all modules

    Returns:
        Dict of module UI component information
    """
    module_ui_info = {}
    modules_base_path = module_manager.modules_path

    logger.info(f"Discovering module UI components in path: {modules_base_path}")

    if not os.path.exists(modules_base_path):
        logger.error(f"Modules path does not exist: {modules_base_path}")
        return module_ui_info

    try:
        for module_dir in os.listdir(modules_base_path):
            if module_dir.endswith("_module"):
                module_name = module_dir.replace("_module", "")
                module_path = os.path.join(modules_base_path, module_dir)

                try:
                    vue_reports = [
                        f for f in os.listdir(module_path) if f.endswith("Report.vue")
                    ]

                    module_ui_info[module_name] = {
                        "has_custom_ui": len(vue_reports) > 0,
                        "ui_component_name": (
                            f"{module_name.capitalize()}Report"
                            if vue_reports
                            else "GenericModule"
                        ),
                        "vue_file_path": (
                            os.path.join(module_path, vue_reports[0])
                            if vue_reports
                            else None
                        ),
                    }

                    logger.debug(
                        f"Found UI component for module {module_name}: {vue_reports[0] if vue_reports else 'None'}"
                    )
                except Exception as e:
                    logger.error(f"Error processing module {module_name}: {str(e)}")
                    continue

        logger.info(f"Discovered UI components for {len(module_ui_info)} modules")
        return module_ui_info

    except Exception as e:
        logger.error(f"Error discovering module UI components: {str(e)}")
        return module_ui_info


@router.get("/module-ui-info")
async def get_module_ui_info():
    """
    Retrieve UI component information for all modules (both internal and external).

    Returns:
    - Dict[str, Dict[str, Any]]: A dictionary mapping module names to their UI information:
        - has_custom_ui (bool): Whether the module has a custom UI component
        - ui_component_name (str): Name of the Vue component to use
        - ui_component_url (str|None): URL to fetch the component from (for external modules)
        - is_external (bool): Whether this is an external module
    """
    try:
        module_ui_info = discover_module_ui_components()

        external_modules = await module_registry.list_modules()
        for module in external_modules:
            module_name = module["module_id"].replace("external_", "")

            if module.get("config", {}).get("has_custom_ui"):
                module_ui_info[module_name] = {
                    "has_custom_ui": True,
                    "ui_component_name": module["config"]
                    .get("ui_component", {})
                    .get("name"),
                    "ui_component_url": f"{module['base_url']}/ui-component",
                    "is_external": True,
                }

        return module_ui_info
    except Exception as e:
        logger.error(f"Error getting module UI info: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to get module UI information"
        )


@router.get("/module-ui-component/{module_name}")
async def get_module_ui_component(module_name: str):
    """
    Retrieve the Vue component contents for a specific module.

    Parameters:
    - module_name (str): Name of the module whose UI component should be retrieved

    Returns:
    - dict: A dictionary containing:
        - module_name (str): Name of the module
        - component_name (str): Name of the Vue component
        - component_content (str): Raw content of the Vue component file
        - is_external (bool): Whether this is an external module

    Raises:
    - 404: If the module or its UI component file is not found
    - 500: If there is an error reading the component file
    """
    try:
        module_ui_info = await get_module_ui_info()
        if module_name not in module_ui_info:
            raise HTTPException(
                status_code=404, detail=f"Module {module_name} not found"
            )

        module_info = module_ui_info[module_name]
        if not module_info.get("has_custom_ui"):
            raise HTTPException(
                status_code=404, detail=f"No custom UI found for module {module_name}"
            )

        if module_info.get("is_external"):
            ui_component_url = module_info.get("ui_component_url")
            if not ui_component_url:
                raise HTTPException(
                    status_code=404,
                    detail=f"No UI component URL found for module {module_name}",
                )

            async with httpx.AsyncClient() as client:
                response = await client.get(ui_component_url)
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Error fetching UI component from external module: {response.text}",
                    )

                component_data = response.json()
                return {
                    "module_name": module_name,
                    "component_name": module_info.get("ui_component_name"),
                    "component_content": component_data.get("component_content"),
                    "is_external": True,
                }
        else:
            if not module_info.get("vue_file_path"):
                raise HTTPException(
                    status_code=404,
                    detail=f"UI component file path not found for module {module_name}",
                )

            if not os.path.exists(module_info["vue_file_path"]):
                raise HTTPException(
                    status_code=404,
                    detail=f"File not found: {module_info['vue_file_path']}",
                )

            with open(module_info["vue_file_path"], "r") as f:
                vue_component_content = f.read()

            return {
                "module_name": module_name,
                "component_name": module_info["ui_component_name"],
                "component_content": vue_component_content,
                "is_external": False,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving UI component for module {module_name}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error retrieving module UI component: {str(e)}"
        )
