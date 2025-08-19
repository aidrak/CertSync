import json
import logging

logger = logging.getLogger(__name__)


class FortiGateCertManager:
    def __init__(self, hostname, api_key, verify_ssl=False):
        self.base_url = f"https://{hostname}/api/v2"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.verify_ssl = verify_ssl

    async def _make_request(
        self, session, method: str, endpoint: str, data=None, timeout: int = 30
    ):
        """Make API request and return (status, response_data)."""
        url = f"{self.base_url}{endpoint}"

        try:
            if method.upper() == "POST":
                response_obj = await session.post(
                    url, headers=self.headers, json=data, timeout=timeout
                )
            elif method.upper() == "GET":
                response_obj = await session.get(url, headers=self.headers, timeout=timeout)
            elif method.upper() == "DELETE":
                response_obj = await session.delete(url, headers=self.headers, timeout=timeout)
            else:
                return None, {"error": "Invalid request method"}

            if response_obj:
                async with response_obj as response:
                    status = response.status
                    try:
                        result_json = await response.json()
                        return status, result_json
                    except json.JSONDecodeError:
                        return status, {"raw_response": await response.text()}
            return None, {"error": "Invalid request method"}

        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None, {"error": str(e)}

    async def check_certificate_exists(self, session, cert_name: str) -> bool:
        """Check if certificate exists."""
        logger.info(f"   Checking if certificate '{cert_name}' exists...")
        status, response = await self._make_request(
            session, "GET", f"/cmdb/vpn.certificate/local/{cert_name}"
        )
        return status == 200

    async def delete_certificate(self, session, cert_name: str) -> bool:
        """Delete certificate."""
        logger.info(f"🗑️ Deleting certificate '{cert_name}'...")
        status, response = await self._make_request(
            session, "DELETE", f"/cmdb/vpn.certificate/local/{cert_name}"
        )
        return status == 200

    def _prepare_certificate_data(self, cert_data) -> dict:
        """
        Prepare certificate data for FortiGate API format.
        This involves stripping PEM headers/footers only - content is already Base64.
        """

        def clean_pem_content(pem_string: str) -> str:
            """Removes PEM headers/footers, content is already Base64 encoded."""
            lines = pem_string.strip().split("\n")
            pem_body_lines = [line for line in lines if not line.startswith("-----")]
            pem_body = "".join(pem_body_lines)
            return pem_body  # Return the already-Base64 content directly

        cert_body_b64 = clean_pem_content(cert_data.cert_body)
        private_key_b64 = clean_pem_content(cert_data.private_key)

        return {
            "type": "local",
            "certname": cert_data.cert_name,
            "key_file_content": private_key_b64,
            "file_content": cert_body_b64,
            "scope": "global",
        }
