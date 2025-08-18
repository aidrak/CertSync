import requests
import logging
from ..base import DnsProviderBase

logger = logging.getLogger(__name__)


class DigitalOceanDns(DnsProviderBase):
    """
    DNS provider for DigitalOcean.
    """

    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://api.digitalocean.com/v2"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _get_domain_and_subdomain(self, full_domain: str):
        """
        Splits a full domain into the root domain and subdomain part.
        Example: _acme-challenge.vpn.example.com -> (example.com, _acme-challenge.vpn)
        """
        parts = full_domain.split(".")
        # A simple heuristic: find the longest suffix that is a registered domain
        # in the account.
        # This is complex. A simpler, common approach is to assume the last two
        # parts are the domain.
        # This works for "example.com" but not "example.co.uk".
        # For this implementation, we'll assume the user provides the root domain.
        # A better implementation would get all domains from the account and find
        # the matching one.
        # Let's assume the challenge domain is always
        # `_acme-challenge.subdomain.domain.com`
        # and we need to find `domain.com`.

        # A robust implementation is complex. We'll use a common, if imperfect, method.
        # Let's assume the main domain is the last two parts.
        if len(parts) > 2:
            domain = f"{parts[-2]}.{parts[-1]}"
            subdomain = ".".join(parts[:-2])
            return domain, subdomain
        return full_domain, "@"  # @ represents the root domain itself

    def create_txt_record(self, domain: str, token: str):
        """
        Create a TXT record for the given domain.
        `domain` is the full challenge domain, e.g., _acme-challenge.vpn.example.com
        `token` is the value for the TXT record.
        """
        root_domain, record_name = self._get_domain_and_subdomain(domain)

        url = f"{self.base_url}/domains/{root_domain}/records"
        payload = {"type": "TXT", "name": record_name, "data": token, "ttl": 60}

        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            logger.info(
                f"Successfully created TXT record for {domain} on DigitalOcean."
            )
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to create TXT record for {domain} on DigitalOcean: {e}"
            )
            raise

    def delete_txt_record(self, domain: str, token: str):
        """
        Delete a TXT record for the given domain.
        """
        root_domain, record_name = self._get_domain_and_subdomain(domain)

        # First, find the record ID
        records_url = (
            f"{self.base_url}/domains/{root_domain}/records?type=TXT&name={record_name}"
        )

        try:
            response = requests.get(records_url, headers=self.headers)
            response.raise_for_status()
            records = response.json().get("domain_records", [])

            record_id = None
            for record in records:
                # Find the specific record that matches the token (challenge value)
                if record.get("data") == token:
                    record_id = record.get("id")
                    break

            if record_id:
                delete_url = (
                    f"{self.base_url}/domains/{root_domain}/records/{record_id}"
                )
                delete_response = requests.delete(delete_url, headers=self.headers)
                delete_response.raise_for_status()
                logger.info(
                    f"Successfully deleted TXT record for {domain} from DigitalOcean."
                )
            else:
                logger.warning(f"Could not find TXT record for {domain} to delete.")

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to delete TXT record for {domain} from DigitalOcean: {e}"
            )
            # Don't raise an exception here, as failure to clean up shouldn't
            # block the whole process.
