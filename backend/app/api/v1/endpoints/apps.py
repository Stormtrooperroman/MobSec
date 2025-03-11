from fastapi import APIRouter, UploadFile, HTTPException, status, Query
from app.core.storage import AsyncStorageService
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
    Upload a mobile application file (APK or IPA) for analysis.
    """
    try:
        file_hash = await storage.handle_uploaded_file(file)
        file_status = await storage.get_scan_status(file_hash)
        
        if file_status['file_type'] == 'unknown':
            await storage.delete_file(file_hash)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file type. Only APK and IPA files are supported."
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
    - file_hash: The unique hash identifier of the file
    - modules: Optional list of module names to filter results
    
    Returns a structured report with file information and scan results.
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
