from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.crud import crud_deployment
from app.schemas import schemas
from app.schemas.certificates import Certificate as CertificateSchema
from app.db.database import get_db
from app.dependencies import require_admin_or_technician
from app.db.models import User, DnsProviderAccount, Certificate, TargetSystem, DeploymentStatus, Deployment
from app.db import models

router = APIRouter(dependencies=[Depends(require_admin_or_technician)])


@router.post("/")
def create_deployment(
    deployment: schemas.DeploymentCreate,
    db: Session = Depends(get_db),
):
    db_deployment = crud_deployment.create_deployment(
        db=db,
        certificate_id=deployment.certificate_id,
        target_system_id=deployment.target_system_id,
        auto_renewal_enabled=deployment.auto_renewal_enabled,
        deployment_config=deployment.deployment_config,
    )
    
    # Manually serialize to avoid schema conflicts (same as read_deployments)
    return {
        "id": db_deployment.id,
        "certificate_id": db_deployment.certificate_id,
        "target_system_id": db_deployment.target_system_id,
        "auto_renewal_enabled": db_deployment.auto_renewal_enabled,
        "status": db_deployment.status,
        "created_at": db_deployment.created_at,
        "updated_at": db_deployment.updated_at,
        "details": db_deployment.details,
        "last_deployed_at": db_deployment.last_deployed_at,
        "next_renewal_date": db_deployment.next_renewal_date,
        "deployment_config": db_deployment.deployment_config,
        "certificate": {
            "id": db_deployment.certificate.id,
            "common_name": db_deployment.certificate.common_name,
            "expires_at": db_deployment.certificate.expires_at,
            "issued_at": db_deployment.certificate.issued_at,
            "dns_provider_account": {
                "id": db_deployment.certificate.dns_provider_account.id,
                "company": db_deployment.certificate.dns_provider_account.company,
                "managed_domain": db_deployment.certificate.dns_provider_account.managed_domain,
                "provider_type": db_deployment.certificate.dns_provider_account.provider_type
            } if db_deployment.certificate.dns_provider_account else None
        } if db_deployment.certificate else None,
        "target_system": {
            "id": db_deployment.target_system.id,
            "system_name": db_deployment.target_system.system_name,
            "system_type": db_deployment.target_system.system_type,
            "public_ip": db_deployment.target_system.public_ip,
            "port": db_deployment.target_system.port,
            "company": db_deployment.target_system.company,
            "admin_username": db_deployment.target_system.admin_username
        } if db_deployment.target_system else None
    }

@router.get("/")
def read_deployments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    deployments = crud_deployment.get_deployments(db, skip=skip, limit=limit)
    
    # Manually serialize to avoid schema conflicts
    result = []
    for deployment in deployments:
        deployment_dict = {
            "id": deployment.id,
            "certificate_id": deployment.certificate_id,
            "target_system_id": deployment.target_system_id,
            "auto_renewal_enabled": deployment.auto_renewal_enabled,
            "status": deployment.status,
            "created_at": deployment.created_at,
            "updated_at": deployment.updated_at,
            "details": deployment.details,
            "last_deployed_at": deployment.last_deployed_at,
            "next_renewal_date": deployment.next_renewal_date,
            "deployment_config": deployment.deployment_config,
            "certificate": {
                "id": deployment.certificate.id,
                "common_name": deployment.certificate.common_name,
                "expires_at": deployment.certificate.expires_at,
                "issued_at": deployment.certificate.issued_at,
                "dns_provider_account": {
                    "id": deployment.certificate.dns_provider_account.id,
                    "company": deployment.certificate.dns_provider_account.company,
                    "managed_domain": deployment.certificate.dns_provider_account.managed_domain,
                    "provider_type": deployment.certificate.dns_provider_account.provider_type
                } if deployment.certificate.dns_provider_account else None
            } if deployment.certificate else None,
            "target_system": {
                "id": deployment.target_system.id,
                "system_name": deployment.target_system.system_name,
                "system_type": deployment.target_system.system_type,
                "public_ip": deployment.target_system.public_ip,
                "port": deployment.target_system.port,
                "company": deployment.target_system.company
            } if deployment.target_system else None
        }
        result.append(deployment_dict)
    
    return result

@router.get("/{deployment_id}", response_model=schemas.Deployment)
def read_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
):
    db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
    if db_deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return db_deployment


@router.post("/{deployment_id}/run")
async def run_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
):
    from ..services.firewall_manager.factory import FirewallManagerFactory
    from ..services.firewall_manager.base import CertificateData
    from ..core.security import decrypt_secret
    import asyncio
    import json
    
    db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
    if db_deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Update status to pending
    crud_deployment.update_deployment_status(db, deployment_id=deployment_id, status=DeploymentStatus.pending)
    
    try:
        # Get certificate and target system details
        certificate = db_deployment.certificate
        target_system = db_deployment.target_system
        
        # Prepare certificate data (use original common name for VPN)
        cert_data = CertificateData(
            cert_name=certificate.common_name,
            cert_body=certificate.certificate_body,
            private_key=decrypt_secret(str(certificate.private_key)),
            chain=None  # TODO: Handle certificate chains if needed
        )
        
        # Get firewall manager (FTP config comes from environment variables)
        firewall_manager = FirewallManagerFactory.get_manager(target_system)
        
        # Default to SSL VPN deployment (can be configurable in the future)
        deployment_type = "ssl_vpn"
        
        # Perform deployment based on type
        if deployment_type == "ssl_vpn":
            # Use VPN-specific deployment
            success = False
            deployment_logs = []
            
            async for message in firewall_manager.deploy_vpn_certificate(cert_data):
                deployment_logs.append(message)
                # You could emit these messages via SSE or websockets if needed
            
            # Check if deployment succeeded (last message should indicate success)
            success = any("SUCCESS" in log or "successful" in log.lower() for log in deployment_logs[-3:])
            
            if success:
                crud_deployment.update_deployment_status(
                    db, 
                    deployment_id=deployment_id, 
                    status=DeploymentStatus.success,
                    details="\n".join(deployment_logs[-10:])  # Store last 10 log messages
                )
                
                # Update last_deployed_at timestamp
                from datetime import datetime
                db.query(models.Deployment).filter(models.Deployment.id == deployment_id).update({
                    "last_deployed_at": datetime.utcnow()
                })
                db.commit()
                
                return {"message": "SSL VPN certificate deployment completed successfully", "logs": deployment_logs}
            else:
                crud_deployment.update_deployment_status(
                    db, 
                    deployment_id=deployment_id, 
                    status=DeploymentStatus.failed,
                    details="\n".join(deployment_logs[-10:])
                )
                return {"message": "SSL VPN certificate deployment failed", "logs": deployment_logs}
        else:
            # Standard certificate import (legacy behavior)
            success = await firewall_manager.import_certificate(cert_data)
            
            if success:
                crud_deployment.update_deployment_status(db, deployment_id=deployment_id, status=DeploymentStatus.success)
                return {"message": "Certificate deployment completed successfully"}
            else:
                crud_deployment.update_deployment_status(db, deployment_id=deployment_id, status=DeploymentStatus.failed)
                return {"message": "Certificate deployment failed"}
                
    except Exception as e:
        # Log the error and update status
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Deployment {deployment_id} failed with error: {str(e)}")
        
        crud_deployment.update_deployment_status(
            db, 
            deployment_id=deployment_id, 
            status=DeploymentStatus.failed,
            details=f"Deployment error: {str(e)}"
        )
        
        raise HTTPException(status_code=500, detail=f"Deployment failed: {str(e)}")

@router.get("/{deployment_id}/run-sse", response_class=StreamingResponse)
async def run_deployment_sse(
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin_or_technician)
):
    """Stream VPN certificate deployment progress via Server-Sent Events"""
    
    async def deployment_stream():
        try:
            from ..services.firewall_manager.factory import FirewallManagerFactory
            from ..services.firewall_manager.base import CertificateData
            from ..core.security import decrypt_secret
            from datetime import datetime
            
            # Get deployment details
            db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
            if db_deployment is None:
                yield "data: ❌ Deployment not found\n\n"
                return
            
            yield "data: 🚀 Starting SSL VPN certificate deployment...\n\n"
            
            # Update status to pending
            crud_deployment.update_deployment_status(db, deployment_id=deployment_id, status=DeploymentStatus.pending)
            yield "data: 📋 Deployment status updated to pending\n\n"
            
            # Get certificate and target system details
            certificate = db_deployment.certificate
            target_system = db_deployment.target_system
            
            yield f"data: 📜 Certificate: {certificate.common_name}\n\n"
            yield f"data: 🎯 Target System: {target_system.system_name} ({target_system.system_type.value})\n\n"
            
            # Prepare certificate data (use original common name for VPN)
            cert_data = CertificateData(
                cert_name=certificate.common_name,
                cert_body=certificate.certificate_body,
                private_key=decrypt_secret(str(certificate.private_key)),
                chain=None
            )
            
            yield f"data: 🔧 Prepared certificate data for: {cert_data.cert_name}\n\n"
            
            # Get firewall manager
            firewall_manager = FirewallManagerFactory.get_manager(target_system)
            yield f"data: 🏭 Initialized {target_system.system_type.value} manager\n\n"
            
            # Track deployment success and logs
            deployment_logs = []
            deployment_success = False
            
            # Stream VPN deployment progress
            async for message in firewall_manager.deploy_vpn_certificate(cert_data):
                deployment_logs.append(message)
                yield f"data: {message}\n\n"
                
                # Check for success indicators in the message
                if "SUCCESS" in message or "successful" in message.lower():
                    deployment_success = True
            
            # Update deployment status based on success
            if deployment_success:
                crud_deployment.update_deployment_status(
                    db, 
                    deployment_id=deployment_id, 
                    status=DeploymentStatus.success,
                    details="\n".join(deployment_logs[-10:])
                )
                
                # Update last_deployed_at timestamp
                db.query(models.Deployment).filter(models.Deployment.id == deployment_id).update({
                    "last_deployed_at": datetime.utcnow()
                })
                db.commit()
                
                yield "data: ✅ Deployment status updated to SUCCESS\n\n"
                yield "data: 💾 Database updated with deployment timestamp\n\n"
                yield "data: 🎉 SSL VPN certificate deployment completed successfully!\n\n"
            else:
                crud_deployment.update_deployment_status(
                    db, 
                    deployment_id=deployment_id, 
                    status=DeploymentStatus.failed,
                    details="\n".join(deployment_logs[-10:])
                )
                yield "data: ❌ Deployment status updated to FAILED\n\n"
                yield "data: 💔 SSL VPN certificate deployment failed\n\n"
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"SSE Deployment {deployment_id} failed with error: {str(e)}")
            
            crud_deployment.update_deployment_status(
                db, 
                deployment_id=deployment_id, 
                status=DeploymentStatus.failed,
                details=f"Deployment error: {str(e)}"
            )
            
            yield f"data: ❌ Deployment failed: {str(e)}\n\n"
    
    return StreamingResponse(
        deployment_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@router.get("/{deployment_id}/verify-vpn-sse", response_class=StreamingResponse)
async def verify_vpn_deployment_sse(
    deployment_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_admin_or_technician)
):
    """Stream VPN certificate verification progress via Server-Sent Events"""
    
    async def verification_stream():
        try:
            from ..services.firewall_manager.factory import FirewallManagerFactory
            
            # Get deployment details
            db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
            if db_deployment is None:
                yield "data: ❌ Deployment not found\n\n"
                return
            
            yield "data: 🔍 Starting VPN certificate verification...\n\n"
            
            # Get target system details
            target_system = db_deployment.target_system
            certificate = db_deployment.certificate
            
            yield f"data: 📜 Certificate: {certificate.common_name}\n\n"
            yield f"data: 🎯 Target System: {target_system.system_name}\n\n"
            
            # Get firewall manager
            firewall_manager = FirewallManagerFactory.get_manager(target_system)
            yield f"data: 🏭 Initialized {target_system.system_type.value} manager\n\n"
            
            # Prepare certificate name (same format as deployment)
            cert_name = certificate.common_name
            yield f"data: 🔧 Verifying certificate: {cert_name}\n\n"
            
            # Stream VPN verification progress
            async for message in firewall_manager.verify_vpn_deployment(cert_name):
                yield f"data: {message}\n\n"
            
            yield "data: ✅ VPN certificate verification completed!\n\n"
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"SSE VPN verification for deployment {deployment_id} failed: {str(e)}")
            
            yield f"data: ❌ VPN verification failed: {str(e)}\n\n"
    
    return StreamingResponse(
        verification_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )

@router.post("/{deployment_id}/verify-vpn")
async def verify_vpn_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
):
    """Verify that a VPN certificate deployment is working correctly."""
    from ..services.firewall_manager.factory import FirewallManagerFactory
    import json
    
    db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
    if db_deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    try:
        # Get target system details
        target_system = db_deployment.target_system
        certificate = db_deployment.certificate
        
        # Get firewall manager (FTP config comes from environment variables)
        firewall_manager = FirewallManagerFactory.get_manager(target_system)
        
        # Prepare certificate name (same format as deployment)
        cert_name = certificate.common_name
        
        # Perform VPN verification
        verification_logs = []
        success = False
        
        async for message in firewall_manager.verify_vpn_deployment(cert_name):
            verification_logs.append(message)
        
        # Check if verification succeeded
        success = any("successful" in log.lower() or "verified" in log.lower() for log in verification_logs[-3:])
        
        return {
            "deployment_id": deployment_id,
            "certificate_name": cert_name,
            "verification_success": success,
            "logs": verification_logs,
            "message": "VPN certificate verification completed"
        }
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"VPN verification for deployment {deployment_id} failed: {str(e)}")
        
        raise HTTPException(status_code=500, detail=f"VPN verification failed: {str(e)}")

@router.delete("/{deployment_id}")
async def delete_deployment(
    deployment_id: int,
    db: Session = Depends(get_db),
):
    """Delete a deployment"""
    db_deployment = crud_deployment.get_deployment(db, deployment_id=deployment_id)
    if db_deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    
    # Delete the deployment
    db.delete(db_deployment)
    db.commit()
    
    return {"message": "Deployment deleted successfully"}

@router.get("/companies/", response_model=List[str])
def get_companies(
    db: Session = Depends(get_db),
):
    """Get distinct companies from DNS provider accounts"""
    companies = db.query(DnsProviderAccount.company).distinct().order_by(DnsProviderAccount.company).all()
    return [company[0] for company in companies]

@router.get("/certificates-by-company/{company}", response_model=List[CertificateSchema])
def get_certificates_by_company(
    company: str,
    db: Session = Depends(get_db),
):
    """Get certificates for a specific company"""
    certificates = db.query(Certificate).join(DnsProviderAccount).filter(DnsProviderAccount.company == company).all()
    return certificates

@router.get("/target-systems-by-company/{company}", response_model=List[schemas.TargetSystem])
def get_target_systems_by_company(
    company: str,
    db: Session = Depends(get_db),
):
    """Get target systems for a specific company"""
    target_systems = db.query(TargetSystem).filter(TargetSystem.company == company).all()
    return target_systems
