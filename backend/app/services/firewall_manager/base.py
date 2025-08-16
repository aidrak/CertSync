from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator

class CertificateData:
    def __init__(self, cert_name: str, cert_body: str, private_key: str, chain: Optional[str] = None):
        self.cert_name = cert_name
        self.cert_body = cert_body
        self.private_key = private_key
        self.chain = chain

class FirewallBase(ABC):
    @abstractmethod
    async def import_certificate(self, cert_data: CertificateData) -> bool:
        """Imports a certificate to the firewall."""
        pass

    @abstractmethod
    async def apply_certificate(self, cert_name: str, service: str) -> bool:
        """Applies a certificate to a specific service on the firewall."""
        pass

    @abstractmethod
    async def commit_changes(self) -> bool:
        """Commits the configuration changes on the firewall."""
        pass

    @abstractmethod
    async def test_connection(self) -> AsyncIterator[str]:
        """Tests the connection to the firewall and yields log messages."""
        yield "This method needs to be implemented"

    # VPN-specific methods
    async def deploy_vpn_certificate(self, cert_data: CertificateData) -> AsyncIterator[str]:
        """
        Deploy certificate to SSL VPN service.
        Default implementation falls back to import + apply.
        VPN managers can override for specialized deployment.
        """
        yield f"🚀 Starting VPN certificate deployment for {cert_data.cert_name}..."
        
        # Default implementation: import certificate then apply to VPN service
        yield "📥 Importing certificate..."
        import_success = await self.import_certificate(cert_data)
        
        if not import_success:
            yield "❌ Certificate import failed"
            return
        
        yield "✅ Certificate imported successfully"
        yield "🔧 Applying certificate to SSL VPN service..."
        
        apply_success = await self.apply_certificate(cert_data.cert_name, "ssl_vpn")
        
        if not apply_success:
            yield "❌ Failed to apply certificate to SSL VPN"
            return
        
        yield "✅ Certificate applied to SSL VPN"
        yield "💾 Committing changes..."
        
        commit_success = await self.commit_changes()
        
        if commit_success:
            yield "✅ Changes committed successfully"
            yield "🎉 VPN certificate deployment completed!"
        else:
            yield "❌ Failed to commit changes"

    async def verify_vpn_deployment(self, cert_name: str) -> AsyncIterator[str]:
        """
        Verify the VPN certificate is correctly deployed.
        Default implementation - VPN managers should override for specific verification.
        """
        yield f"🔍 Verifying VPN certificate '{cert_name}' deployment..."
        yield "⚠️ Default verification - check firewall manually"
        yield "✅ VPN certificate verification completed (manual check required)"
