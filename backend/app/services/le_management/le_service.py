import asyncio
import logging
import os
from datetime import datetime, timedelta

from acme import challenges, client, jose, messages
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ..dns_providers.base import DnsProviderBase

logger = logging.getLogger(__name__)

LE_STAGING_DIR = "https://acme-staging-v02.api.letsencrypt.org/directory"
LE_PROD_DIR = "https://acme-v02.api.letsencrypt.org/directory"


class LetsEncryptService:
    def __init__(self, email: str, dns_provider: DnsProviderBase, staging: bool = True):
        self.logs = []
        self._log(f"🚀 Initializing LetsEncryptService for {email} (Staging: {staging})")

        self.email = email
        self.dns_provider = dns_provider
        self.directory_url = LE_STAGING_DIR if staging else LE_PROD_DIR
        self.account_resource = None

        try:
            self.account_key = self._get_or_create_account_key()
            self.net = client.ClientNetwork(self.account_key, user_agent="CertSync")
            directory = client.ClientV2.get_directory(self.directory_url, self.net)
            self.client = client.ClientV2(directory, net=self.net)
            self._register_account()
        except Exception as e:
            self._log(f"❌ Initialization failed: {e}")
            raise

    def _log(self, message: str):
        """Log a message and add it to the internal log list."""
        logger.debug(message)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def _get_or_create_account_key(self) -> jose.JWKRSA:
        key_path = os.getenv("ACME_ACCOUNT_KEY_PATH", "/etc/certsync/acme_account_key.pem")
        key_dir = os.path.dirname(key_path)
        os.makedirs(key_dir, exist_ok=True)

        if os.path.exists(key_path):
            self._log("🔑 Found existing ACME account key.")
            with open(key_path, "rb") as f:
                key_pem = f.read()
            private_key = serialization.load_pem_private_key(key_pem, password=None)
        else:
            self._log("🔑 No ACME account key found, creating a new one.")
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            with open(key_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
            os.chmod(key_path, 0o600)
            self._log("✅ New ACME account key created.")

        return jose.JWKRSA(key=private_key)

    def _register_account(self):
        from acme import errors

        self._log("👤 Verifying ACME account...")
        try:
            regr = messages.NewRegistration.from_data(
                email=self.email, terms_of_service_agreed=True
            )
            self.account_resource = self.client.new_account(regr)
            self.net.account = self.account_resource
            self._log("✅ New ACME account registered.")
        except errors.ConflictError as e:
            self._log(f"✅ Existing ACME account found. Retrieving from: {e.location}")
            try:
                # If account exists, retrieve it using only_return_existing
                existing_regr = messages.NewRegistration.from_data(
                    email=self.email,
                    terms_of_service_agreed=True,
                    only_return_existing=True,
                )
                self.account_resource = self.client.new_account(existing_regr)
                self.net.account = self.account_resource
                self._log("✅ Successfully retrieved existing account.")
            except Exception as retrieval_e:
                self._log(f"ℹ️ Standard account retrieval failed: {retrieval_e}. Using fallback.")
                # Fallback: reconstruct minimal account resource from exception URL
                if hasattr(e, "location") and e.location:
                    self._log("🔧 Reconstructing account resource from existing account URL...")
                    account_body = messages.Registration(key=self.account_key.key)
                    self.account_resource = messages.RegistrationResource(
                        body=account_body, uri=e.location
                    )
                    self.net.account = self.account_resource
                    self._log("✅ Account resource reconstructed successfully.")
                else:
                    raise Exception("Could not retrieve account; no location URL provided.")
        except Exception as e:
            self._log(f"❌ Failed during account registration: {e}")
            raise

    def generate_private_key(self) -> rsa.RSAPrivateKey:
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def generate_csr(self, private_key: rsa.RSAPrivateKey, domains: list[str]) -> bytes:
        from cryptography.hazmat.primitives import hashes

        builder = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])]))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(domain) for domain in domains]),
                critical=False,
            )
        )
        return builder.sign(private_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)

    def _get_dns_challenge(self, authz):
        """Extract the DNS-01 challenge from an authorization resource."""
        for challenge in authz.body.challenges:
            if isinstance(challenge.chall, challenges.DNS01):
                return challenge
        self._log("❌ No DNS-01 challenge found.")
        return None

    async def request_certificate(self, domains: list[str]) -> tuple[str, str, str, list[str]]:
        self._log(f"🚀 Starting certificate request for: {', '.join(domains)}")

        private_key = self.generate_private_key()
        csr_pem = self.generate_csr(private_key, domains)
        self._log("✅ Private key and CSR generated.")

        order = self.client.new_order(csr_pem)
        self._log("✅ Order created. Authorizations retrieved.")

        for authz in getattr(order, "authorizations", []):
            domain = authz.body.identifier.value
            self._log(f"📋 Processing authorization for {domain}...")

            dns_challenge = self._get_dns_challenge(authz)
            if not dns_challenge:
                raise Exception(f"DNS-01 challenge not found for {domain}")

            response, validation = dns_challenge.chall.response_and_validation(self.account_key)
            validation_domain_name = f"_acme-challenge.{domain}"

            try:
                self._log("🔧 Creating TXT record for DNS challenge...")
                self.dns_provider.create_txt_record(validation_domain_name, validation)
                self._log("✅ TXT record created. Waiting for propagation...")

                await asyncio.sleep(30)

                self._log("📢 Answering challenge...")
                self.client.answer_challenge(dns_challenge, response)
                self._log("✅ Challenge answered.")

            finally:
                self._log("🧹 Cleaning up TXT record...")
                try:
                    self.dns_provider.delete_txt_record(validation_domain_name, validation)
                    self._log("✅ TXT record cleaned up.")
                except Exception as cleanup_error:
                    self._log(f"⚠️ Failed to cleanup DNS record: {cleanup_error}")

        self._log("⏳ Finalizing order...")
        deadline = datetime.now() + timedelta(minutes=5)
        finalized_order = await asyncio.to_thread(
            self.client.poll_and_finalize, order, deadline=deadline
        )

        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        self._log("🎉 Certificate generated successfully!")
        return private_key_pem, finalized_order.fullchain_pem, "", self.logs
