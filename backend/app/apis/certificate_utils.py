import logging
import json
import traceback
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.crud import crud_dns, crud_log, crud_hostname, crud_certificate
from app.schemas import certificates as cert_schema, schemas
from app.services.le_management.le_service import LetsEncryptService
from app.services.dns_providers.factory import DnsProviderFactory
from app.services.log_streamer import log_streamer
from app.core.config import settings
from app.core.security import decrypt_secret
from app.db.models import User
import sys # <--- ADD THIS IMPORT

logger = logging.getLogger(__name__)

async def handle_certificate_request(
    cert_request: cert_schema.CertificateRequest,
    db: Session,
    current_user: User
):
    print("DEBUG_GLOBAL: ENTERING handle_certificate_request") # <--- AGGRESSIVE PRINT
    sys.stdout.flush() # <--- FORCE FLUSH
    """
    Handles and streams the common logic for requesting a Let's Encrypt certificate.
    This is an async generator that yields log messages.
    """
    fqdn = cert_request.domains[0]
    logger.info(f"--- Starting certificate request for {fqdn} ---")
    yield f"🚀 Starting certificate request for {fqdn}..."
    try:
        # 1. Get DNS Provider Account from DB
        logger.info("Step 1: Fetching DNS Provider Account...")
        yield "📋 Step 1: Fetching DNS Provider Account..."
        dns_account = crud_dns.get_dns_provider_account(db, account_id=cert_request.dns_provider_account_id)
        if not dns_account:
            yield f"❌ Error: DNS Provider Account not found."
            db.rollback()
            return
        yield f"✅ Found DNS account: {dns_account.name}"

        # 2. Decrypt credentials
        logger.info("Step 2: Decrypting credentials...")
        yield "📋 Step 2: Decrypting credentials..."
        try:
            decrypted_creds = decrypt_secret(dns_account.credentials)
            credentials = json.loads(decrypted_creds) if decrypted_creds.startswith('{') else {"token": decrypted_creds}
            yield "✅ Credentials decrypted."
        except Exception as e:
            yield f"❌ Error processing credentials: {e}"
            db.rollback()
            return

        # 3. Create DNS Provider instance
        logger.info("Step 3: Initializing DNS provider...")
        yield "📋 Step 3: Initializing DNS provider..."
        try:
            dns_provider = DnsProviderFactory.get_provider(
                provider_type=dns_account.provider_type,
                credentials=credentials,
                domain=dns_account.domain
            )
            yield f"✅ DNS provider '{dns_account.provider_type}' initialized."
        except Exception as e:
            yield f"❌ Error creating DNS provider: {e}"
            db.rollback()
            return

        # 4. Create LetsEncrypt Service instance
        logger.info("Step 4: Initializing Let's Encrypt service...")
        yield "📋 Step 4: Initializing Let's Encrypt service..."
        try:
            dynamic_email = f"lets-encrypt@{fqdn}"
            le_service = LetsEncryptService(
                email=dynamic_email,
                dns_provider=dns_provider,
                staging=settings.LE_STAGING
            )
            yield "✅ Let's Encrypt service initialized."
        except Exception as e:
            yield f"❌ Error creating Let's Encrypt service: {e}"
            db.rollback()
            return

        # 5. Request Certificate
        logger.info("Step 5: Requesting certificate from Let's Encrypt...")
        yield "📋 Step 5: Requesting certificate from Let's Encrypt... (this may take a moment)"
        
        private_key, cert_body, _, logs = None, None, None, [] # Initialize to avoid UnboundLocalError
        try:
            yield "🔍 DEBUG: Getting hostname from database..."
            hostname = crud_hostname.get_hostname(db, hostname_id=cert_request.hostname_id)
            if not hostname:
                yield f"❌ Error: Hostname not found for ID {cert_request.hostname_id}."
                db.rollback()
                return
            
            fqdn = hostname.hostname
            domains = [fqdn] + [d for d in cert_request.domains if d != fqdn]
            yield f"🔍 DEBUG: Requesting certificate for domains: {domains}"
            
            print("DEBUG_GLOBAL: CALLING le_service.request_certificate") # <--- AGGRESSIVE PRINT
            sys.stdout.flush() # <--- FORCE FLUSH

            private_key, cert_body, _, logs = await le_service.request_certificate(domains)
            
            print("DEBUG_GLOBAL: RETURNED from le_service.request_certificate. PK_len:", len(private_key) if private_key else 'N/A', "Cert_len:", len(cert_body) if cert_body else 'N/A', "Logs_count:", len(logs)) # <--- AGGRESSIVE PRINT
            sys.stdout.flush() # <--- FORCE FLUSH

            # >>> CRITICAL NEW DEBUGGING LINES (already there, but for context) <<<
            logger.debug(f"DEBUG_AFTER_LE_CALL: LE service completed. PK_len: {len(private_key) if private_key else 'N/A'}, Cert_len: {len(cert_body) if cert_body else 'N/A'}, Logs_count: {len(logs)}.")
            yield f"🔍 DEBUG_POST_LE: Execution continued after LE call. PK_len={len(private_key) if private_key else 'N/A'}, Cert_len={len(cert_body) if cert_body else 'N/A'}, Logs_count={len(logs)}."
            # >>> END CRITICAL NEW DEBUGGING LINES <<<

            # Immediately check for None/empty data that might cause errors later
            if not private_key or not cert_body:
                yield "❌ Critical: LE service returned empty private key or cert body."
                logger.error("Critical: LE service returned empty private key or cert body, aborting save.")
                db.rollback()
                return

            yield f"🔍 DEBUG: LE service returned {len(logs)} log messages."
            yield f"🔍 DEBUG: About to iterate and log LE messages. current_user.id: {current_user.id}"

            # New: Try-except around the log creation loop
            try:
                for idx, log_message in enumerate(logs):
                    yield f"🔍 DEBUG: Processing LE log message {idx+1}: {log_message}"
                    # Ensure log message isn't too long if your DB column has a limit
                    truncated_message = (log_message[:997] + '...') if len(log_message) > 1000 else log_message
                    crud_log.create_log(db, log=schemas.LogCreate(level="info", action="Request LE Certificate", target=fqdn, message=truncated_message), user_id=current_user.id)
                yield "✅ All LE log messages processed."
            except Exception as e_log_loop:
                yield f"❌ CRITICAL ERROR during LE log message processing: {e_log_loop}"
                yield f"🔍 DEBUG: Log processing traceback: {traceback.format_exc()}"
                crud_log.create_log(db, log=schemas.LogCreate(level="error", action="Process LE Logs", target=fqdn, message=f"Error in log loop: {e_log_loop}"), user_id=current_user.id)
                db.rollback()
                return
            
            logger.info("--- Certificate generation completed, proceeding to save... ---")
            yield "🔍 DEBUG: Certificate generation completed, proceeding to save..."

        except Exception as e_le_request: # This catches errors directly from le_service.request_certificate itself
            error_message = f"❌ Error requesting LE certificate: {e_le_request}"
            yield error_message
            yield f"🔍 DEBUG: Full traceback for LE request: {traceback.format_exc()}"
            crud_log.create_log(db, log=schemas.LogCreate(level="error", action="Request Certificate", target=fqdn, message=str(e_le_request)), user_id=current_user.id)
            db.rollback()
            return
            
        # 6. Save certificate to DB
        logger.info("Step 6: Saving certificate to database...")
        yield "📋 Step 6: Saving certificate to database..."
        
        # New: Try-except around the save operations
        try:
            logger.debug(f"About to save certificate with name='{cert_request.name}', common_name='{fqdn}'")
            logger.debug(f"Certificate body length: {len(cert_body)} chars")
            logger.debug(f"Private key length: {len(private_key)} chars")
            logger.debug(f"Hostname ID: {cert_request.hostname_id}")
            yield f"🔍 DEBUG: About to save certificate with name='{cert_request.name}', common_name='{fqdn}'"
            yield f"🔍 DEBUG: Certificate body length: {len(cert_body)} chars"
            yield f"🔍 DEBUG: Private key length: {len(private_key)} chars"
            yield f"🔍 DEBUG: Hostname ID: {cert_request.hostname_id}"
            
            if not cert_body or not private_key:
                yield "❌ Error: Missing certificate data from LE service (cert_body or private_key is empty)"
                db.rollback()
                return
                
            if not cert_request.name or not fqdn:
                yield "❌ Error: Missing certificate name or domain"
                db.rollback()
                return
            
            yield f"🔍 DEBUG: Inputs validated, calling create_certificate..."
            logger.debug("Inputs validated, calling create_certificate...")
            
            db_certificate = crud_certificate.create_certificate(
                db=db,
                name=cert_request.name,
                common_name=cert_request.domains[0],
                certificate_body=cert_body,
                private_key=private_key
            )
            
            logger.debug(f"Certificate model created. Now attempting to update hostname.")
            yield f"🔍 DEBUG: Certificate model created. Now attempting to update hostname."
            
            hostname_update = cert_schema.HostnameUpdate(certificate_id=db_certificate.id)
            updated_hostname = crud_hostname.update_hostname(db=db, hostname_id=cert_request.hostname_id, hostname=hostname_update)
            
            logger.debug(f"Hostname updated. Certificate ID linked: {updated_hostname.certificate_id if updated_hostname else 'None'}")
            yield f"🔍 DEBUG: Hostname updated. Certificate ID linked: {updated_hostname.certificate_id if updated_hostname else 'None'}"
            
            logger.info("Committing all changes to database (certificate, hostname, logs)...")
            yield "🔍 DEBUG: Committing all changes to database..."
            db.commit()
            
            db.refresh(db_certificate)
            if updated_hostname:
                db.refresh(updated_hostname)
            
            logger.info(f"Successfully saved certificate ID {db_certificate.id} and linked to hostname.")
            success_message = f"✅ Certificate ID {db_certificate.id} saved and linked to hostname."
            yield success_message
            
            crud_log.create_log(db, log=schemas.LogCreate(level="info", action="Request Certificate", target=fqdn, message="Successfully generated and saved certificate."), user_id=current_user.id)
            
            yield f"🎉 Certificate generated successfully for {fqdn}!"

        except Exception as e_save:
            logger.error(f"Error saving certificate to database: {e_save}", exc_info=True)
            yield f"❌ Error saving certificate to database: {e_save}"
            yield f"🔍 DEBUG: Full error traceback during save: {traceback.format_exc()}"
            crud_log.create_log(db, log=schemas.LogCreate(level="error", action="Save Certificate", target=fqdn, message=f"Failed to save to DB: {e_save}"), user_id=current_user.id)
            db.rollback()
            return
            
    except Exception as e_overall:
        yield f"❌ An unexpected error occurred: {e_overall}"
        logger.error(f"Unexpected error in handle_certificate_request: {e_overall}\n{traceback.format_exc()}")
        crud_log.create_log(db, log=schemas.LogCreate(level="error", action="Request Certificate", target=fqdn, message=f"Unexpected overall error: {e_overall}"), user_id=current_user.id)
        db.rollback()
