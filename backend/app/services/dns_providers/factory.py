import importlib
import logging
from .base import DnsProviderBase

logger = logging.getLogger(__name__)

class DnsProviderFactory:
    @staticmethod
    def get_provider(provider_type, credentials: dict, domain: str) -> DnsProviderBase:
        from ...db.models import DnsProviderType
        provider_name = provider_type.value
        try:
            module = importlib.import_module(f".{provider_name}.provider", package="app.services.dns_providers")
            provider_class = getattr(module, f"{provider_name.capitalize()}Dns")

            # This is the key fix: The credentials object from the API is a dictionary,
            # but the validator expects the raw token string.
            if isinstance(credentials, dict):
                token = credentials.get("token")
            else:
                # Fallback for safety, though the API layer should ensure it's a dict.
                token = credentials
                
            return provider_class(token=token, domain=domain)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Unsupported DNS provider: {provider_name}") from e

    @staticmethod
    def get_validator(provider_type, credentials: dict, domain: str):
        from ...db.models import DnsProviderType
        provider_name = provider_type.value
        try:
            module = importlib.import_module(f".{provider_name}.validator", package="app.services.dns_providers")
            validator_class = getattr(module, f"{provider_name.capitalize()}TokenTester")
            return validator_class(api_token=credentials.get("token"), domain=domain)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Unsupported DNS provider validator: {provider_name}") from e
