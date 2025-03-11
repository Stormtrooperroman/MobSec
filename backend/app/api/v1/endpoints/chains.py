import os
import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import Response
from app.modules.module_manager import ModuleManager
from app.modules.chain_manager import ChainManager
import yaml


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

router = APIRouter()

module_manager = ModuleManager(
    redis_url=os.getenv('REDIS_URL'),
    modules_path=os.getenv('MODULES_PATH')
)

chain_manager = ChainManager()

@router.get("/")
async def get_all_chains():
    """Retrieve all chains with their modules."""
    chains = await chain_manager.get_all_chains()
    return chains

@router.post("/")
async def create_chain(chain_data: Dict[str, Any] = Body(...)):
    try:
        if 'name' not in chain_data:
            raise HTTPException(status_code=400, detail="Chain name is required")
            
        new_chain = await chain_manager.create_chain(chain_data)
        return new_chain
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating chain: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating chain")

@router.get("/{chain_name}")
async def get_chain(chain_name: str):
    """Retrieve a chain by name with its modules."""
    chain = await chain_manager.get_chain_by_name(chain_name)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain

@router.put("/{chain_name}")
async def update_chain(chain_name: str, chain_data: Dict[str, Any] = Body(...)):
    """Update a chain by name."""
    try:
        updated_chain = await chain_manager.update_chain(chain_name, chain_data)
        if not updated_chain:
            raise HTTPException(status_code=404, detail="Chain not found")
        return updated_chain
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating chain: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating chain")

@router.delete("/{chain_name}")
async def delete_chain(chain_name: str):
    """Delete a chain by name."""
    try:
        success = await chain_manager.delete_chain(chain_name)
        if not success:
            raise HTTPException(status_code=404, detail="Chain not found")
        return {"message": "Chain deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting chain: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting chain")

@router.post("/{chain_name}/run")
async def run_chain(
    chain_name: str,
    file_hash: str = Body(..., embed=True)
):
    """
    Run a specific analysis chain for an uploaded file.
    
    Parameters:
    - chain_name: Name of the chain to run
    - file_hash: Hash of the file to process
    
    Returns:
    - task_id: ID for tracking the chain execution task
    """
    try:
        result = await chain_manager.run_chain(chain_name, file_hash)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error running chain '{chain_name}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to run chain: {str(e)}")

@router.get("/{chain_name}/export")
async def export_chain(chain_name: str):
    """Export a chain to YAML format"""
    try:
        chain = await chain_manager.get_chain_by_name(chain_name)
        if not chain:
            raise HTTPException(status_code=404, detail="Chain not found")
        
        # Format chain data for YAML export
        export_data = {
            "name": chain["name"],
            "description": chain["description"],
            "modules": [
                {
                    "name": module["module"]["name"],
                    "order": module["order"],
                    "parameters": module["parameters"]
                }
                for module in chain["modules"]
            ]
        }
        
        # Convert to YAML
        yaml_content = yaml.dump(export_data, sort_keys=False, allow_unicode=True)
        
        # Return as downloadable file
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f'attachment; filename="{chain_name}.yaml"'
            }
        )
    except Exception as e:
        logger.error(f"Error exporting chain: {str(e)}")
        raise HTTPException(status_code=500, detail="Error exporting chain")