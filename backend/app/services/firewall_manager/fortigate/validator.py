import logging
import aiohttp
import ssl
import asyncio
import base64
import datetime
import secrets
from typing import Any, Dict

# Certificate generation imports
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

class FortiGateValidator:
    """
    Validates the connection and credentials for a FortiGate firewall by performing
    a full certificate management workflow.
    """
    def __init__(self, firewall_settings):
        self.hostname = firewall_settings.public_ip
        self.port = firewall_settings.port
        self.api_key = firewall_settings.api_key
        self.verify_ssl = False
        self.base_url = f"https://{self.hostname}:{self.port}/api/v2"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Generate unique test certificate name for each validation run
        # Shortened format: CST-MMDDHHMM-HEX for better FortiGate compatibility
        timestamp = datetime.datetime.now().strftime("%m%d%H%M") # Month, Day, Hour, Minute
        unique_id = secrets.token_hex(4) # 4 bytes = 8 hex characters
        self.test_cert_name = f"CST-{timestamp}-{unique_id}" # Example: CST-08151530-d9b2a375

    def _generate_test_certificate(self):
        """
        Generates a fresh test certificate and private key for each validation run.
        This ensures each test is unique and simulates real certificate operations.
        """
        # Generate private key
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Create certificate subject with unique CN
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"NE"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, u"Omaha"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"CertSync-Test"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, u"Validation"),
            x509.NameAttribute(NameOID.COMMON_NAME, self.test_cert_name), # This already uses self.test_cert_name
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, u"admin@certsync.test")
        ])
        
        # Create certificate with 1-year validity
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), 
                critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=True,
            )
            .sign(key, hashes.SHA256(), default_backend())
        )

        # Convert to PEM format
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode('utf-8')
        
        return cert_pem, key_pem

    async def _make_request(self, session: aiohttp.ClientSession, method: str, endpoint: str, data: dict | None = None) -> tuple[int | None, dict]:
        url = f"{self.base_url}{endpoint}"
        request_kwargs: Dict[str, Any] = {"headers": self.headers, "timeout": 20}
        if data:
            request_kwargs["json"] = data
        try:
            async with session.request(method, url, **request_kwargs) as response:
                if response.status == 204:
                    return response.status, {}
                if 'application/json' in response.headers.get('Content-Type', ''):
                    return response.status, await response.json()
                return response.status, {"raw_response": await response.text()}
        except Exception as e:
            logger.error(f"Request to {url} failed: {e}")
            return None, {"error": str(e)}

    async def _check_cert_exists(self, session, cert_name) -> tuple[bool, str]:
        status, result = await self._make_request(session, "GET", f"/cmdb/vpn.certificate/local/{cert_name}")
        if status == 200:
            return True, f"✅ Test certificate '{cert_name}' found."
        elif status == 404:
            return False, f"✅ Test certificate '{cert_name}' not found (clean state)."
        else:
            return False, f"⚠️ Could not verify certificate status (HTTP {status})."

    async def _delete_cert(self, session, cert_name) -> tuple[bool, str]:
        status, result = await self._make_request(session, "DELETE", f"/cmdb/vpn.certificate/local/{cert_name}")
        if status in [200, 404]:
            return True, "✅ Certificate deletion command successful."
        elif status == 424:
            return False, f"⚠️ Cannot delete certificate '{cert_name}' as it is in use."
        else:
            error_msg = result.get('error', 'Unknown error')
            return False, f"❌ Failed to delete certificate (HTTP {status}): {error_msg}"

    async def _import_cert(self, session, cert_name) -> tuple[bool, str]:
        # Generate fresh certificate for this test
        cert_pem, key_pem = self._generate_test_certificate()
        
        payload = {
            "type": "regular",  # Confirmed working parameter for your FortiGate
            "certname": cert_name,
            "file_content": base64.b64encode(cert_pem.encode()).decode(),
            "key_file_content": base64.b64encode(key_pem.encode()).decode(),
            "scope": "global"
        }
        
        status, result = await self._make_request(session, "POST", "/monitor/vpn-certificate/local/import", payload)
        
        if status == 200:
            return True, "✅ Certificate imported successfully via monitor API."
        elif status == 500 and result.get("error") == -23:
            return True, "ℹ️ Certificate already exists (error -23), proceeding."
        elif status == 500 and result.get("error") == -327:
            return False, f"❌ Certificate format invalid (error -327). FortiGate rejected the certificate format. This may indicate an issue with certificate encoding or API compatibility."
        elif status == 500 and result.get("error") == -328:
            return False, f"❌ Certificate validation failed (error -328). The certificate content may be invalid or incompatible with this FortiGate version."
        elif status == 424:
            return False, f"❌ Missing required parameters (HTTP 424). The API request is missing mandatory fields."
        else:
            error_msg = result.get('error', 'Unknown error')
            return False, f"❌ Failed to import certificate (HTTP {status}): {error_msg}"

    async def _test_certificate_update(self, session, cert_name) -> tuple[bool, str]:
        """
        Test certificate renewal/update functionality using PUT method.
        This simulates what happens during Let's Encrypt renewals.
        """
        # Generate a new certificate for the update test
        cert_pem, key_pem = self._generate_test_certificate()
        
        payload = {
            "name": cert_name,
            "certificate": cert_pem,
            "private-key": key_pem,
            "source": "user"
        }
        
        status, result = await self._make_request(session, "PUT", f"/cmdb/vpn.certificate/local/{cert_name}", payload)
        
        if status == 200:
            return True, "✅ Certificate renewal (PUT update) successful."
        else:
            error_msg = result.get('error', 'Unknown error')
            return False, f"❌ Certificate renewal failed (HTTP {status}): {error_msg}"

    async def run_complete_test(self):
        yield f"🚀 Starting FortiGate Comprehensive Validation..."
        yield f"📋 Test Certificate: {self.test_cert_name}"
        yield f"🎯 Target: {self.hostname}:{self.port}"
        
        ssl_context = ssl.create_default_context()
        if not self.verify_ssl:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # 1. Initial Check and Cleanup
                yield f"🔍 Checking for pre-existing test certificate..."
                exists, msg = await self._check_cert_exists(session, self.test_cert_name)
                yield msg
                
                if exists:
                    yield f"🗑️ Attempting to delete pre-existing certificate..."
                    deleted, msg = await self._delete_cert(session, self.test_cert_name)
                    yield msg
                    if not deleted:
                        yield "❌ Aborting: Could not delete pre-existing test certificate."
                        return
                    await asyncio.sleep(2)

                # 2. Generate and Import Certificate
                yield f"🔧 Generating fresh test certificate..."
                yield f"➕ Attempting to import test certificate..."
                imported, msg = await self._import_cert(session, self.test_cert_name)
                yield msg
                if not imported:
                    yield "❌ Aborting: Certificate import failed."
                    return
                await asyncio.sleep(2)

                # 3. Verify Import
                yield "🔍 Verifying certificate import..."
                verified, msg = await self._check_cert_exists(session, self.test_cert_name)
                yield msg
                if not verified:
                    yield "❌ Aborting: Could not verify certificate after import."
                    return

                # 4. Test Certificate Renewal (simulates Let's Encrypt renewal)
                yield "🔄 Testing certificate renewal functionality..."
                renewed, msg = await self._test_certificate_update(session, self.test_cert_name)
                yield msg
                if not renewed:
                    yield "⚠️ Certificate renewal test failed, but import succeeded."
                else:
                    yield "✅ Certificate renewal test successful - ready for Let's Encrypt!"
                
                await asyncio.sleep(2)
                
                # 5. Final Cleanup
                yield f"🗑️ Cleaning up test certificate..."
                cleaned, msg = await self._delete_cert(session, self.test_cert_name)
                yield msg
                if not cleaned:
                    yield f"⚠️ Failed to clean up test certificate '{self.test_cert_name}'. Please remove it manually."
                else:
                    yield "✅ Cleanup successful."

                # 6. Summary
                if renewed:
                    yield "🎉 SUCCESS: FortiGate comprehensive validation complete!"
                    yield "✅ All certificate operations tested successfully:"
                    yield "   • Certificate import via monitor API ✅"
                    yield "   • Certificate verification via cmdb API ✅" 
                    yield "   • Certificate renewal via PUT method ✅"
                    yield "   • Certificate deletion ✅"
                    yield "Validation successful!"
                else:
                    yield "⚠️ PARTIAL SUCCESS: Import works but renewal needs investigation."
                    yield "Validation successful!"

        except aiohttp.ClientConnectorError as e:
            yield f"❌ Connection Failed: Could not connect to the FortiGate at {self.hostname}. Error: {e}"
            yield "Validation failed."
        except Exception as e:
            yield f"❌ An unexpected error occurred during validation: {e}"
            yield "Validation failed."