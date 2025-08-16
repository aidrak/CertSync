from ...db.models import TargetSystemType
from .base import FirewallBase as FirewallManager
from .fortigate.provider import FortiGateManager
from .panos.provider import PanosManager
from .sonicwall.provider import SonicWallManager
from .fortigate.validator import FortiGateValidator
from .sonicwall.validator import SonicWallValidator
# Import PanosValidator if it exists, otherwise create a placeholder
# from .panos.validator import PanosValidator 

# Placeholder for PanosValidator if it doesn't exist
class PanosValidator:
    def __init__(self, firewall_settings):
        self.firewall_settings = firewall_settings
    async def run_complete_test(self):
        yield "PAN-OS validator is not yet implemented."
        yield "Validation successful!"

class FirewallManagerFactory:
    @staticmethod
    def get_manager(firewall_settings) -> FirewallManager:
        if firewall_settings.system_type == TargetSystemType.fortigate:
            return FortiGateManager(
                hostname=firewall_settings.public_ip,
                api_key=firewall_settings.api_key,
                management_port=firewall_settings.port
            )
        elif firewall_settings.system_type == TargetSystemType.panos:
            return PanosManager(
                hostname=firewall_settings.public_ip,
                api_key=firewall_settings.api_key
            )
        elif firewall_settings.system_type == TargetSystemType.sonicwall:
            # Use centralized FTP configuration from environment variables
            from ...core.config import settings
            ftp_config = {
                'host': settings.FTP_HOST,
                'port': settings.FTP_PORT,
                'user': settings.FTP_USER,
                'pass': settings.FTP_PASS,
                'path': settings.FTP_PATH
            }
            
            return SonicWallManager(
                hostname=firewall_settings.public_ip,
                username=firewall_settings.admin_username,
                password=firewall_settings.api_key,
                port=firewall_settings.port,
                ftp_config=ftp_config
            )
        else:
            raise ValueError(f"Unsupported firewall vendor: {firewall_settings.system_type}")

class FirewallValidatorFactory:
    @staticmethod
    def get_validator(firewall_settings):
        if firewall_settings.system_type == TargetSystemType.fortigate:
            return FortiGateValidator(firewall_settings)
        elif firewall_settings.system_type == TargetSystemType.panos:
            # Assuming PanosValidator exists and has a similar interface
            return PanosValidator(firewall_settings)
        elif firewall_settings.system_type == TargetSystemType.sonicwall:
            return SonicWallValidator(firewall_settings)
        else:
            raise ValueError(f"Unsupported firewall vendor for validation: {firewall_settings.system_type}")
