from __future__ import annotations
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body, Request, BackgroundTasks
from sqlalchemy.orm import Session
import json
import traceback
import asyncio
from threading import Thread

from app.crud import crud_certificate, crud_dns, crud_log
from app.schemas import certificates as cert_schema, schemas as generic_schema
from app.db.database import get_db, SessionLocal
from app.services.le_management.le_service import LetsEncryptService
from app.services.dns_providers.factory import DnsProviderFactory
from app.services.log_streamer import log_streamer
from app.core.config import settings
from app.core.security import decrypt_secret
from app.dependencies import require_role, require_admin_or_technician, get_current_user, get_current_user_sse
from app.db.models import UserRole, User, Certificate
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt

router = APIRouter()
logger = logging.getLogger(__name__)


# Background task function for saving certificates
def save_certificate_to_db(cert_data: dict, user_id: int, renewal_cert_id: int = None):
    """Background task to save certificate to database"""
    db = SessionLocal()
    try:
        if renewal_cert_id:
            logger.info(f"Background task: Renewing certificate ID {renewal_cert_id} with new data for {cert_data.get('common_name')}")
            
            # Update the existing certificate
            certificate = crud_certificate.update_certificate(
                db=db,
                certificate_id=renewal_cert_id,
                certificate_body=cert_data['certificate_body'],
                private_key=cert_data['private_key']
            )
            
            if not certificate:
                raise Exception(f"Certificate with ID {renewal_cert_id} not found for renewal")
            
            action = "Certificate Renewed"
            message = "Certificate successfully renewed and updated in database"
            logger.info(f"Background task: Certificate {cert_data['common_name']} renewed successfully")
        else:
            logger.info(f"Background task: Saving new certificate {cert_data.get('common_name')} to database")
            
            # Save the certificate
            certificate = crud_certificate.create_certificate(
                db=db,
                common_name=cert_data['common_name'],
                certificate_body=cert_data['certificate_body'],
                private_key=cert_data['private_key'],
                dns_provider_account_id=cert_data['dns_provider_account_id']
            )
            
            action = "Certificate Created"
            message = "Certificate successfully created and saved to database"
            logger.info(f"Background task: Certificate {cert_data['common_name']} saved successfully with ID {certificate.id}")
        
        db.commit()
        
        # Log the success
        crud_log.create_log(
            db=db,
            log=generic_schema.LogCreate(
                level="info",
                action=action,
                target=f"Certificate: {cert_data['common_name']}",
                message=message
            ),
            user_id=user_id
        )
        
    except Exception as e:
        error_action = "Certificate Renewal Failed" if renewal_cert_id else "Certificate Creation Failed"
        logger.error(f"Background task: Failed to {'renew' if renewal_cert_id else 'save'} certificate: {str(e)}")
        db.rollback()
        
        # Log the error
        try:
            crud_log.create_log(
                db=db,
                log=generic_schema.LogCreate(
                    level="error",
                    action=error_action,
                    target=f"Certificate: {cert_data.get('common_name', 'Unknown')}",
                    message=f"Failed to {'renew' if renewal_cert_id else 'save'} certificate to database: {str(e)}"
                ),
                user_id=user_id
            )
        except:
            pass
    finally:
        db.close()


# Modified certificate request handler that separates streaming from DB operations
async def handle_certificate_request_streaming(cert_request, user_id: int, background_tasks: BackgroundTasks, renewal_cert_id: int = None):
    """Handle certificate request with streaming updates and background DB save"""
    
    try:
        yield "data: 🚀 Starting certificate request...\n\n"
        await asyncio.sleep(0.1)
        
        yield "data: 🔍 Validating request parameters...\n\n"
        await asyncio.sleep(0.1)
        
        # Create a new session for the certificate generation only
        db = SessionLocal()
        try:
            # Get DNS provider details
            dns_provider = crud_dns.get_dns_provider_account(db, account_id=cert_request.dns_provider_account_id)
            if not dns_provider:
                yield "data: ❌ DNS provider not found\n\n"
                return
            
            provider_name = str(dns_provider.provider_type).split('.')[-1].capitalize()
            yield f"data: ✅ Using DNS provider: {provider_name}\n\n"
            await asyncio.sleep(0.1)
            
            # Initialize services
            yield "data: 🔧 Initializing Let's Encrypt service...\n\n"
            await asyncio.sleep(0.1)
            
            # Create DNS provider factory
            dns_factory = DnsProviderFactory()
            dns_service = dns_factory.get_provider(
                provider_type=dns_provider.provider_type,
                credentials=json.loads(decrypt_secret(str(dns_provider.credentials))),
                domain=str(dns_provider.managed_domain)
            )
            
            # Initialize Let's Encrypt service
            le_service = LetsEncryptService(
                email=settings.LE_EMAIL,
                dns_provider=dns_service,
                staging=settings.LE_STAGING
            )
            
            yield "data: 🌐 Requesting certificate from Let's Encrypt...\n\n"
            await asyncio.sleep(0.1)
            
            # Run the certificate request in a thread pool to avoid blocking
            def run_certificate_request():
                return le_service.request_certificate(
                    domains=cert_request.domains
                )
            
            # Execute in thread pool
            loop = asyncio.get_event_loop()
            private_key, certificate_body, _, logs = await loop.run_in_executor(
                None, asyncio.run, run_certificate_request()
            )
            
            if certificate_body and private_key:
                yield "data: ✅ Certificate generated successfully!\n\n"
                await asyncio.sleep(0.1)
                
                # Prepare certificate data for background task
                cert_data = {
                    'common_name': cert_request.domains[0],  # First domain as common name
                    'certificate_body': certificate_body,
                    'private_key': private_key,
                    'dns_provider_account_id': cert_request.dns_provider_account_id,
                }
                
                # Schedule background task to save to database
                background_tasks.add_task(save_certificate_to_db, cert_data, user_id, renewal_cert_id)
                
                yield "data: 💾 Certificate queued for database save...\n\n"
                await asyncio.sleep(0.1)
                
                yield "data: 🎉 Certificate request completed successfully!\n\n"
                
            else:
                yield "data: ❌ Failed to generate certificate\n\n"
                
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error in certificate request streaming: {str(e)}")
        yield f"data: ❌ Error: {str(e)}\n\n"


# Updated SSE endpoint using background tasks
@router.post("/request-le-cert-sse/{dns_provider_name}", response_class=StreamingResponse)
async def request_le_certificate_sse(
    dns_provider_name: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("technician"))
) -> StreamingResponse:
    """Stream certificate request progress via Server-Sent Events"""
    logger.info(f"--- SSE endpoint hit for {dns_provider_name} ---")
    
    async def event_stream():
        try:
            logger.info("--- Starting event_stream ---")
            # Get the request body
            body = await request.body()
            logger.info(f"Request body: {body}")
            data = json.loads(body)
            
            # Extract certificate request data
            cert_request_data = data.get('cert_request', {})
            cert_request = cert_schema.CertificateRequest(**cert_request_data)
            logger.info(f"Parsed certificate request: {cert_request}")
            
            # Call the certificate handler and stream the results
            logger.info("--- Calling handle_certificate_request_streaming ---")
            async for message in handle_certificate_request_streaming(cert_request, int(current_user.id), background_tasks):
                yield message
                
            logger.info("--- Finished handle_certificate_request_streaming ---")
                
        except Exception as e:
            logger.error(f"Error in certificate SSE stream: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            yield f"data: ❌ Error: {str(e)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


# Alternative GET endpoint for SSE (updated with background tasks)
@router.get("/request-le-cert-sse/{dns_provider_name}")
async def request_le_certificate_sse_get(
    dns_provider_name: str,
    domains: str,  # comma-separated
    dns_provider_account_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("technician"))
) -> StreamingResponse:
    """Stream certificate request progress via Server-Sent Events (GET version)"""
    
    async def event_stream():
        try:
            # Create certificate request from query parameters
            domains_list = [d.strip() for d in domains.split(',')]
            cert_request = cert_schema.CertificateRequest(
                domains=domains_list,
                dns_provider_account_id=dns_provider_account_id
            )
            
            # Call the certificate handler and stream the results
            async for message in handle_certificate_request_streaming(cert_request, int(current_user.id), background_tasks):
                yield message
                
        except Exception as e:
            logger.error(f"Error in certificate SSE stream: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            yield f"data: ❌ Error: {str(e)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


@router.get("/renew-le-cert-sse/{dns_provider_name}")
async def renew_certificate_sse_get(
    dns_provider_name: str,
    cert_id: int,
    domains: str,
    dns_provider_account_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_sse)
):
    """
    SSE endpoint for certificate renewal using GET method.
    This will overwrite the existing certificate with a new one.
    """
    logger.info(f"--- SSE renewal endpoint hit for {dns_provider_name} ---")
    
    async def event_stream():
        try:
            logger.info("--- Starting renewal event_stream ---")
            
            # Get the existing certificate to validate and get details
            existing_cert = crud_certificate.get_certificate(db, certificate_id=cert_id)
            if not existing_cert:
                yield f"data: ❌ Certificate with ID {cert_id} not found\n\n"
                return
            
            # Create certificate request data for renewal
            domains_list = [d.strip() for d in domains.split(',')]
            cert_request = cert_schema.CertificateRequest(
                domains=domains_list,
                dns_provider_account_id=dns_provider_account_id
            )
            
            logger.info(f"Renewing certificate ID {cert_id} with request: {cert_request}")
            
            # Use the same streaming handler but with renewal context
            yield f"data: 🔄 Renewing certificate for {domains_list[0]}...\n\n"
            
            async for message in handle_certificate_request_streaming(cert_request, int(current_user.id), background_tasks, renewal_cert_id=cert_id):
                yield message
                
            logger.info("--- Finished renewal handle_certificate_request_streaming ---")
                
        except Exception as e:
            logger.error(f"Error in certificate renewal SSE stream: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            yield f"data: ❌ Renewal Error: {str(e)}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )


@router.get("/", response_model=List[cert_schema.Certificate])
def read_certificates(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_technician)):
    logger.debug(f"Reading certificates with skip: {skip}, limit: {limit}")
    certificates = crud_certificate.get_certificates(db, skip=skip, limit=limit)
    return certificates


@router.get("/{cert_id}", response_model=cert_schema.Certificate)
def read_certificate(cert_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_technician)):
    logger.debug(f"Reading certificate with ID: {cert_id}")
    db_cert = crud_certificate.get_certificate(db, certificate_id=cert_id)
    if db_cert is None:
        logger.warning(f"Certificate with ID {cert_id} not found.")
        raise HTTPException(status_code=404, detail="Certificate not found")
    return db_cert


@router.delete("/{cert_id}", status_code=200)
def delete_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("technician"))
):
    logger.info(f"--- Attempting to delete certificate ID: {cert_id} by user '{current_user.username}' with role '{current_user.role}' ---")
    
    db_cert = crud_certificate.get_certificate(db, certificate_id=cert_id)
    if db_cert is None:
        logger.warning(f"Certificate with ID {cert_id} not found for deletion.")
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    # Check for associated deployments
    if db_cert.deployments:
        logger.warning(f"User '{current_user.username}' attempted to delete certificate ID {cert_id}, but it is tied to active deployments.")
        raise HTTPException(status_code=400, detail="Cannot delete a certificate tied to an active deployment. Please delete the deployment and try again.")

    logger.info(f"Found certificate '{db_cert.common_name}' for deletion.")
    
    crud_certificate.delete_certificate(db, certificate_id=cert_id)
    logger.info("Certificate marked for deletion in the database session.")
    
    db.commit()
    logger.info(f"--- Certificate ID {cert_id} successfully deleted from the database. ---")
    
    return {"message": "Certificate deleted successfully"}


@router.post("/{cert_id}/download/", response_class=StreamingResponse)
def download_certificate(
    cert_id: int,
    data: cert_schema.PasswordData,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_technician)
):
    logger.debug(f"User '{current_user.username}' attempting to download certificate ID {cert_id}.")
    db_cert = crud_certificate.get_certificate(db, certificate_id=cert_id)
    if db_cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")

    if db_cert.certificate_body is None or db_cert.private_key is None:
        raise HTTPException(status_code=400, detail="Certificate data is incomplete.")

    try:
        pfx_data = crud_certificate.create_pfx(
            db,
            certificate_id=cert_id,
            password=data.password
        )
        
        filename = f"{db_cert.common_name}.pfx"
        return StreamingResponse(
            iter([pfx_data]),
            media_type="application/x-pkcs12",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error(f"Failed to create PFX for cert ID {cert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create PFX file.")
