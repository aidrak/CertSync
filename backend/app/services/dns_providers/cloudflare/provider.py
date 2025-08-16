import logging
from ..base import DnsProviderBase
from .validator import CloudflareTokenTester

logger = logging.getLogger(__name__)

class CloudflareDns(DnsProviderBase):
    def __init__(self, token: str, domain: str):
        logger.debug(f"CloudflareDns received token: {token}")
        logger.debug(f"CloudflareDns token type: {type(token)}")
        self.tester = CloudflareTokenTester(api_token=token, domain=domain)
        # We still want to validate the token on initialization
        if not self.tester.test_token_validity() or not self.tester.test_zone_access():
             raise Exception("Cloudflare token validation failed.")

    def create_txt_record(self, domain: str, token: str):
        logger.info(f"Creating TXT record for {domain} with token {token}")
        record_data = {
            "type": "TXT",
            "name": domain,
            "content": token,
            "ttl": 120
        }
        success, result = self.tester._make_request("POST", f"/zones/{self.tester.zone_id}/dns_records", record_data)
        if not success:
            error_msg = result.get('errors', [{}])[0].get('message', 'Unknown error')
            raise Exception(f"Failed to create TXT record: {error_msg}")
        logger.info(f"Successfully created TXT record for {domain}")

    def delete_txt_record(self, domain: str, token: str):
        logger.info(f"Deleting TXT record for {domain}")
        # First, find the record ID
        success, result = self.tester._make_request("GET", f"/zones/{self.tester.zone_id}/dns_records?type=TXT&name={domain}")
        if not success:
            error_msg = result.get('errors', [{}])[0].get('message', 'Unknown error')
            logger.warning(f"Could not retrieve TXT records for deletion: {error_msg}")
            return

        records = result.get("result", [])
        record_id = None
        for record in records:
            if record.get("content") == token:
                record_id = record.get("id")
                break
        
        if not record_id:
            logger.warning(f"Could not find TXT record for {domain} to delete.")
            return

        # Delete the record
        success, result = self.tester._make_request("DELETE", f"/zones/{self.tester.zone_id}/dns_records/{record_id}")
        if not success:
            error_msg = result.get('errors', [{}])[0].get('message', 'Unknown error')
            logger.warning(f"Failed to delete TXT record: {error_msg}")
        else:
            logger.info(f"Successfully deleted TXT record for {domain}")
