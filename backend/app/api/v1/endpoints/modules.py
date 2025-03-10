from fastapi import APIRouter, HTTPException, status, Body
from typing import Dict, List, Any, Optional
import logging
from app.modules.module_manager import ModuleManager
import os
import docker
from app.core.storage import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

router = APIRouter()

module_manager = ModuleManager(
    redis_url=os.getenv('REDIS_URL'),
    modules_path=os.getenv('MODULES_PATH')
)

@router.get("/")
async def list_modules() -> List[Dict]:
    """
    Get information and status of all modules in a format matching the frontend requirements
    """
    try:
        modules_info = []
        docker_client = docker.from_env()
        
        # Get list of all module directories
        modules = [d for d in os.listdir(module_manager.modules_path) 
                  if os.path.isdir(os.path.join(module_manager.modules_path, d))]
        
        for module_name in modules:
            container_name = f"mobsec_{module_name}"
            
            # Get module configuration
            module_config = module_manager.modules_config.get(module_name, {})
            
            module_info = {
                "id": module_config.get("id", module_name),  # Use config ID if available, else use name
                "name": module_config.get("display_name", module_name),
                "description": module_config.get("description", "No description available"),
                "active": False
            }
            
            try:
                container = docker_client.containers.get(container_name)
                module_info["active"] = container.status == "running"
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.error(f"Error checking container status for {module_name}: {str(e)}")
                
            modules_info.append(module_info)
            
        return modules_info
        
    except Exception as e:
        logger.error(f"Error listing modules: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing modules: {str(e)}"
        )

@router.post("/{module_id}/toggle")
async def toggle_module(module_id: str) -> Dict:
    try:
        module_name = None
        for name, config in module_manager.modules_config.items():
            if str(config.get("id", name)) == module_id:
                module_name = name
                break
                
        if not module_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module with ID {module_id} not found"
            )
            
        container_name = f"mobsec_{module_name}"
        try:
            container = module_manager.docker_client.containers.get(container_name)
            if container.status == "running":
                await module_manager.stop_module(module_name)
                return {
                    "status": "success",
                    "message": f"Module {module_name} deactivated",
                    "active": False
                }
            else:
                await module_manager.start_module(module_name)
                return {
                    "status": "success",
                    "message": f"Module {module_name} activated",
                    "active": True
                }
        except docker.errors.NotFound:
            logger.info(f"No existing container found with name: {container_name}")
            await module_manager.start_module(module_name)
            return {
                "status": "success",
                "message": f"Module {module_name} activated",
                "active": True
            }

            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling module: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error toggling module: {str(e)}"
        )



@router.post("/{module_name}/run")
async def run_module(
    module_name: str,
    request: Dict[str, Any] = Body(..., example={"file_hash": "hash123"})
):
    """Run a specific module on a file"""
    try:
        file_hash = request.get("file_hash")
        if not file_hash:
            raise HTTPException(
                status_code=422,
                detail="file_hash is required in request body"
            )
        
        # Check if module exists
        if not await module_manager.check_module_exists(module_name):
            raise HTTPException(
                status_code=404,
                detail=f"Module '{module_name}' not found or not active"
            )
        
        # Get file info from storage service
        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(
                status_code=404,
                detail=f"File with hash '{file_hash}' not found"
            )
        
        # Ensure folder_path exists and is valid
        folder = file_info.get("folder_path", "")
        if not folder:
            # Fallback folder construction
            original_name = file_info.get("original_name", "unknown")
            folder = "_".join(original_name.split('.')[0].split()) + '-' + file_hash
            
        # Prepare data for the module
        data = {
            "folder_path": folder,
            "file_name": file_info.get("original_name", ""),
            "file_type": file_info.get("file_type", "unknown")
        }
        
        logger.info(f"Submitting task for module {module_name} with data: {data}")
        
        # Submit task to the module
        task_id = await module_manager.submit_task(module_name, data, file_hash)
        
        if not task_id:
            raise HTTPException(
                status_code=500,
                detail="Failed to create task"
            )
            
        return {
            "status": "success", 
            "message": f"{module_name} task submitted for file {file_hash}",
            "task_id": task_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting {module_name} task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit task: {str(e)}"
        )



def discover_module_ui_components(modules_base_path: str = '/app/modules') -> Dict[str, Dict[str, Any]]:
    """
    Dynamically discover module UI components across all modules
    
    Args:
        modules_base_path (str): Base path where modules are stored
    
    Returns:
        Dict of module UI component information
    """
    module_ui_info = {}
    
    # Iterate through all module directories
    for module_dir in os.listdir(modules_base_path):
        if module_dir.endswith('_module'):
            module_name = module_dir.replace('_module', '')
            module_path = os.path.join(modules_base_path, module_dir)
            
            # Look for Vue files ending with Report.vue
            vue_reports = [f for f in os.listdir(module_path) if f.endswith('Report.vue')]
            
            module_ui_info[module_name] = {
                "has_custom_ui": len(vue_reports) > 0,
                "ui_component_name": f"{module_name.capitalize()}Report" if vue_reports else "GenericModule",
                "vue_file_path": os.path.join(module_path, vue_reports[0]) if vue_reports else None
            }
    
    return module_ui_info

@router.get("/module-ui-info")
async def get_module_ui_info():
    """
    Endpoint to retrieve module UI component information
    """
    try:
        module_ui_info = discover_module_ui_components()
        return module_ui_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error discovering module UIs: {str(e)}")

@router.get("/module-ui-component/{module_name}")
async def get_module_ui_component(module_name: str):
    """
    Endpoint to retrieve the contents of a specific module's UI component
    """
    try:
        module_ui_info = discover_module_ui_components()
        module_name = module_name.replace('_module', '')
        if module_ui_info.get(module_name, "") == "":
            raise HTTPException(status_code=404, detail=f"Module {module_name} not found")
        
        module_info = module_ui_info[module_name]
        
        if not module_info['has_custom_ui']:
            raise HTTPException(status_code=404, detail=f"No custom UI found for module {module_name}")
        
        # Read the Vue file contents
    

        if module_info['vue_file_path'] is None:
            raise HTTPException(status_code=404, detail=f"UI component file is missing for {module_name}")

        if not os.path.exists(module_info['vue_file_path']):
            raise HTTPException(status_code=404, detail=f"File not found: {module_info['vue_file_path']}")


        with open(module_info['vue_file_path'], 'r') as f:
            vue_component_content = f.read()
        
        return {
            "module_name": module_name,
            "component_name": module_info['ui_component_name'],
            "component_content": vue_component_content
        }
    
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"UI component file not found for module {module_name}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving module UI component: {str(e)}")
