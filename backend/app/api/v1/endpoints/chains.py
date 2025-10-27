import logging
import os
from typing import Any, Dict

import yaml
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import Response

from app.modules.chain_manager import ChainManager
from app.modules.module_manager import ModuleManager


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

router = APIRouter()

module_manager = ModuleManager(
    redis_url=os.getenv("REDIS_URL"), modules_path=os.getenv("MODULES_PATH")
)

chain_manager = ChainManager()


@router.get("/")
async def get_all_chains():
    """
    Retrieve all chains with their modules.

    Returns:
    - List[dict]: A list of chains, each containing:
        - name (str): Name of the chain
        - description (str): Description of the chain's purpose
        - modules (List[dict]): List of modules in the chain, each containing:
            - module (dict): Module information
                - name (str): Name of the module
                - description (str): Module description
            - order (int): Execution order in the chain
            - parameters (dict): Module-specific parameters

    Raises:
    - 500: If there is an error retrieving the chains
    """
    chains = await chain_manager.get_all_chains()
    return chains


@router.post("/")
async def create_chain(chain_data: Dict[str, Any] = Body(...)):
    """
    Create a new chain.

    Parameters:
    - chain_data (Dict[str, Any]): Chain configuration containing:
        - name (str): Name of the chain (required)
        - description (str): Description of the chain's purpose
        - modules (List[dict]): List of modules to include:
            - name (str): Name of the module
            - order (int): Execution order in the chain
            - parameters (dict): Module-specific parameters

    Returns:
    - dict: The created chain configuration with all its details

    Raises:
    - 400: If chain name is missing or if chain data is invalid
    - 500: If there is an error creating the chain
    """
    try:
        if "name" not in chain_data:
            raise HTTPException(status_code=400, detail="Chain name is required")

        new_chain = await chain_manager.create_chain(chain_data)
        return new_chain

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error creating chain: %s", str(e))
        raise HTTPException(status_code=500, detail="Error creating chain") from e


@router.get("/{chain_name}")
async def get_chain(chain_name: str):
    """
    Retrieve a specific chain by name.

    Parameters:
    - chain_name (str): Name of the chain to retrieve

    Returns:
    - dict: Chain configuration containing:
        - name (str): Name of the chain
        - description (str): Description of the chain's purpose
        - modules (List[dict]): List of modules in the chain, each containing:
            - module (dict): Module information
            - order (int): Execution order
            - parameters (dict): Module-specific parameters

    Raises:
    - 404: If the chain with the given name is not found
    """
    chain = await chain_manager.get_chain_by_name(chain_name)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain


@router.put("/{chain_name}")
async def update_chain(chain_name: str, chain_data: Dict[str, Any] = Body(...)):
    """
    Update a existing chain.

    Parameters:
    - chain_name (str): Name of the chain to update
    - chain_data (Dict[str, Any]): Updated chain configuration containing:
        - description (str): New description for the chain
        - modules (List[dict]): Updated list of modules:
            - name (str): Name of the module
            - order (int): New execution order
            - parameters (dict): Updated module parameters

    Returns:
    - dict: The updated chain configuration

    Raises:
    - 404: If the chain with the given name is not found
    - 400: If the update data is invalid
    - 500: If there is an error updating the chain
    """
    try:
        updated_chain = await chain_manager.update_chain(chain_name, chain_data)
        if not updated_chain:
            raise HTTPException(status_code=404, detail="Chain not found")
        return updated_chain
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error updating chain: %s", str(e))
        raise HTTPException(status_code=500, detail="Error updating chain") from e


@router.delete("/{chain_name}")
async def delete_chain(chain_name: str):
    """
    Delete a chain.

    Parameters:
    - chain_name (str): Name of the chain to delete

    Returns:
    - dict: A dictionary containing:
        - message (str): Confirmation message of successful deletion

    Raises:
    - 404: If the chain with the given name is not found
    - 500: If there is an error deleting the chain
    """
    try:
        success = await chain_manager.delete_chain(chain_name)
        if not success:
            raise HTTPException(status_code=404, detail="Chain not found")
        return {"message": "Chain deleted successfully"}
    except Exception as e:
        logger.error("Error deleting chain: %s", str(e))
        raise HTTPException(status_code=500, detail="Error deleting chain") from e


@router.post("/{chain_name}/run")
async def run_chain(chain_name: str, file_hash: str = Body(..., embed=True)):
    """
    Run a specific chain for an uploaded file.

    Parameters:
    - chain_name (str): Name of the chain to execute
    - file_hash (str): Hash of the file to analyze

    Returns:
    - dict: A dictionary containing:
        - task_id (str): Unique identifier for tracking the chain execution
        - status (str): Initial status of the chain execution
        - message (str): Description of the action taken

    Raises:
    - 404: If the chain or file is not found
    - 500: If there is an error running the chain
    """
    try:
        result = await chain_manager.run_chain(chain_name, file_hash)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error("Error running chain '%s': %s", chain_name, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to run chain: {str(e)}") from e


@router.get("/{chain_name}/export")
async def export_chain(chain_name: str):
    """
    Export a chain to YAML format.

    Parameters:
    - chain_name (str): Name of the chain to export

    Returns:
    - Response: YAML file containing the chain configuration:
        - name (str): Chain name
        - description (str): Chain description
        - modules (List[dict]): List of modules with their configuration:
            - name (str): Module name
            - order (int): Execution order
            - parameters (dict): Module parameters

    Raises:
    - 404: If the chain with the given name is not found
    - 500: If there is an error exporting the chain
    """
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
                    "parameters": module["parameters"],
                }
                for module in chain["modules"]
            ],
        }

        # Convert to YAML
        yaml_content = yaml.dump(export_data, sort_keys=False, allow_unicode=True)

        # Return as downloadable file
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f'attachment; filename="{chain_name}.yaml"'
            },
        )
    except Exception as e:
        logger.error("Error exporting chain: %s", str(e))
        raise HTTPException(status_code=500, detail="Error exporting chain") from e
