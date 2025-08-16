from abc import ABC, abstractmethod

class DnsProviderBase(ABC):
    @abstractmethod
    def create_txt_record(self, domain: str, token: str):
        """Create a TXT record for DNS-01 challenge."""
        pass

    @abstractmethod
    def delete_txt_record(self, domain: str, token: str):
        """Delete a TXT record after DNS-01 challenge."""
        pass
