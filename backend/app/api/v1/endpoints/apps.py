from fastapi import APIRouter, UploadFile, HTTPException, status, Query
from app.core.app_manager import AsyncStorageService
from typing import List
from datetime import datetime

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

router = APIRouter()
storage = AsyncStorageService()

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile):
    """
    Upload a mobile application file (APK, IPA or ZIP) for analysis.

    Parameters:
    - file (UploadFile): The application file to be uploaded and analyzed

    Returns:
    - dict: A dictionary containing:
        - file_hash (str): Unique hash identifier for the uploaded file
        - file_type (str): Detected type of the file (apk/ipa/zip)
        - status (str): Status of the upload operation ('accepted')

    Raises:
    - 400: If the uploaded file type is not supported
    - 500: If there is an error processing the file upload
    """
    try:
        file_hash = await storage.handle_uploaded_file(file)
        file_status = await storage.get_scan_status(file_hash)
        
        if file_status['file_type'] == 'unknown':
            await storage.delete_file(file_hash)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only APK, IPA or ZIP files are supported."
            )
            
        
        return {
            "file_hash": file_hash,
            "file_type": file_status['file_type'],
            "status": "accepted"
        }
        
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing file upload"
        )

@router.get("/status/{file_hash}")
async def get_scan_status(file_hash: str):
    """
    Get the current status and results of a file scan.

    Parameters:
    - file_hash (str): The unique hash identifier of the file to check

    Returns:
    - dict: A dictionary containing scan status information:
        - file_hash (str): The file's unique identifier
        - scan_status (str): Current status of the scan
        - timestamp (str): Time when the file was uploaded
        - file_type (str): Type of the uploaded file
        - original_name (str): Original filename
        - scan_results (dict): Results from completed module scans

    Raises:
    - 404: If the file with the given hash is not found
    - 500: If there is an error retrieving the scan status
    """
    try:
        status = await storage.get_scan_status(file_hash)
        if not status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving scan status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving scan status"
        )

@router.get("/report/{file_hash}")
async def get_report(
    file_hash: str, 
    modules: List[str] = Query(None, description="Filter results by specific modules")
):
    """
    Get a comprehensive report for the scanned file.
    
    Parameters:
    - file_hash (str): The unique hash identifier of the file
    - modules (List[str], optional): List of specific module names to filter results

    Returns:
    - dict: A comprehensive report containing:
        - file_info (dict):
            - hash (str): File's unique identifier
            - name (str): Original filename
            - file_type (str): Type of the file
            - size (int): File size in bytes
            - upload_time (str): Timestamp of upload
            - hashes (dict): Various file hashes
        - scan_info (dict):
            - status (str): Overall scan status
            - started_at (str): Scan start timestamp
            - completed_at (str): Scan completion timestamp
            - duration (str): Total scan duration
        - modules (dict): Results from each module
        - summary (dict):
            - total_modules_run (int): Number of modules executed
            - modules_completed (int): Number of completed module scans
            - generated_at (str): Report generation timestamp

    Raises:
    - 404: If the file is not found
    - 500: If there is an error generating the report
    """
    try:
        # Get file status and scan results
        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        
        # Check if scan has completed
        if file_info.get('scan_status') not in ['completed', 'failed']:
            return {
                "file_hash": file_hash,
                "scan_status": file_info.get('scan_status'),
                "message": "Scan is still in progress or hasn't started",
                "file_info": file_info
            }
        
        scan_results = {}
        all_results = await storage.get_scan_status(file_hash)
        if not all_results or not all_results.get('scan_results'):
            return {
                "file_hash": file_hash,
                "scan_status": file_info.get('scan_status'),
                "message": "No scan results available",
                "file_info": file_info,
                "results": {}
            }
        
        all_scan_results = all_results.get('scan_results', {})
        
        if modules:
            scan_results = {
                module: result for module, result in all_scan_results.items()
                if module in modules
            }
        else:
            scan_results = all_scan_results
        
        # Build comprehensive report
        report = {
            "file_info": {
                "hash": file_info.get('file_hash'),
                "name": file_info.get('original_name'),
                "file_type": file_info.get('file_type'),
                "size": file_info.get('size'),
                "upload_time": file_info.get('timestamp'),
                "hashes": file_info.get('hashes', {})
            },
            "scan_info": {
                "status": file_info.get('scan_status'),
                "started_at": file_info.get('scan_started_at'),
                "completed_at": file_info.get('scan_completed_at'),
                "duration": None
            },
            "modules": {
                module: {
                    "results": result.get('results'),
                }
                for module, result in scan_results.items()
            },
            "summary": {
                "total_modules_run": len(scan_results),
                "modules_completed": sum(1 for result in scan_results.values() 
                                       if result.get('status') == 'success' or result.get('status') == 'completed'),
                "generated_at": datetime.now().isoformat()
            }
        }
        
        if file_info.get('scan_started_at') and file_info.get('scan_completed_at'):
            start = file_info.get('scan_started_at')
            end = file_info.get('scan_completed_at')
            if isinstance(start, str):
                start = datetime.fromisoformat(start.replace('Z', '+00:00'))
            if isinstance(end, str):
                end = datetime.fromisoformat(end.replace('Z', '+00:00'))
            
            duration_seconds = (end - start).total_seconds()
            report["scan_info"]["duration"] = f"{duration_seconds:.2f} seconds"
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )

@router.delete("/{file_hash}")
async def delete_file(file_hash: str):
    """
    Delete a file and its associated scan results.

    Parameters:
    - file_hash (str): The unique hash identifier of the file to delete

    Returns:
    - dict: A dictionary containing:
        - status (str): 'success' if the deletion was successful
        - message (str): Confirmation message

    Raises:
    - 404: If the file with the given hash is not found
    - 500: If there is an error during file deletion
    """
    try:
        success = await storage.delete_file(file_hash)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found"
            )
        

        return {"status": "success", "message": "File deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting file"
        )

@router.get("/")
async def list_files(skip: int = 0, limit: int = 10):
    """
    List all uploaded files with their current scan status.

    Parameters:
    - skip (int, optional): Number of records to skip for pagination. Defaults to 0
    - limit (int, optional): Maximum number of records to return. Defaults to 10

    Returns:
    - dict: A dictionary containing:
        - total (int): Total number of files in the system
        - skip (int): Number of records skipped
        - limit (int): Maximum number of records returned
        - apps (List[dict]): List of file records, each containing:
            - file_hash (str): Unique identifier
            - original_name (str): Original filename
            - upload_time (str): Timestamp of upload
            - scan_status (str): Current status of analysis
            - file_type (str): Type of the file

    Raises:
    - 500: If there is an error retrieving the file list
    """
    try:
        files = await storage.list_files(skip=skip, limit=limit)
        total = await storage.get_total_files()
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "apps": files
        }
        
    except Exception as e:
        logger.error(f"Error listing apps: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving file list"
        )
