"""
Centralized exception handling for consistent error responses
"""
import logging
from typing import Dict, Any
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class CertSyncError(Exception):
    """Base exception for CertSync application"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class ValidationError(CertSyncError):
    """Validation related errors"""
    def __init__(self, message: str):
        super().__init__(message, 400)

class NotFoundError(CertSyncError):
    """Resource not found errors"""
    def __init__(self, resource: str):
        super().__init__(f"{resource} not found", 404)

class ConflictError(CertSyncError):
    """Resource conflict errors"""
    def __init__(self, message: str):
        super().__init__(message, 409)

class ExternalServiceError(CertSyncError):
    """External service communication errors"""
    def __init__(self, service: str, action: str):
        super().__init__(f"Failed to {action} via {service}", 502)

def handle_generic_exception(e: Exception, operation: str, resource: str = None) -> HTTPException:
    """
    Convert exceptions to consistent HTTPException responses
    Logs detailed error server-side, returns generic message to client
    """
    # Log the detailed error for debugging
    logger.error(f"Error during {operation}: {str(e)}", exc_info=True)
    
    # Return generic error message to client
    if resource:
        detail = f"Failed to {operation} {resource}"
    else:
        detail = f"Failed to {operation}"
    
    return HTTPException(status_code=500, detail=detail)

def handle_sse_exception(e: Exception, operation: str) -> str:
    """
    Handle exceptions in SSE streams consistently
    Logs detailed error, returns generic SSE message
    """
    logger.error(f"SSE error during {operation}: {str(e)}", exc_info=True)
    return f"data: ❌ Failed to {operation}\n\n"
