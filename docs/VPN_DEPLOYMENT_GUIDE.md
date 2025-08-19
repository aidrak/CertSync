# SSL VPN Certificate Deployment Guide

## Overview

The CertSync system now supports automated SSL VPN certificate deployment to FortiGate and SonicWall firewalls. This functionality extracts and integrates the tested logic from your working `forti-vpn.py` and `sonic-vpn.py` scripts.

## Supported Platforms

### FortiGate Firewalls
- **Certificate Import**: Uses FortiGate REST API for certificate import
- **SSL VPN Configuration**: Automatically assigns certificate to SSL VPN service
- **Verification**: Confirms SSL VPN is using the new certificate
- **Requirements**: API key with appropriate permissions

### SonicWall Firewalls
- **Certificate Import**: Uses FTP upload + CLI import method
- **SSL VPN Configuration**: Supports multiple SonicOS versions (6.x and 7.x)
- **Verification**: Checks certificate assignment via CLI commands
- **Requirements**: Admin credentials and FTP server access

## How to Use

### 1. Create a Deployment
1. Navigate to the **Deployments** page
2. Click **Add Deployment**
3. Select:
   - Company (filters certificates and target systems)
   - Certificate (issued SSL certificate)
   - Target System (configured firewall)
4. Enable **Auto-Renewal** if desired
5. Click **Add Deployment**

### 2. Deploy to SSL VPN
1. In the deployments table, locate your deployment
2. Click the **Deploy** button
3. The system will:
   - Import the certificate to the firewall
   - Configure it as the SSL VPN certificate
   - Commit changes (where applicable)
   - Verify the deployment

### 3. Verify VPN Certificate
1. After deployment, click **Verify VPN**
2. This will:
   - Check that the certificate is properly assigned
   - Confirm SSL VPN service is using the new certificate
   - Report verification status

## Configuration

### Centralized FTP Server
The system uses a centralized FTP server running in the container to serve all clients. The FTP configuration is managed through environment variables:

```bash
# FTP Server Configuration (in .env file)
FTP_HOST=ftp-server
FTP_PORT=21
FTP_USER=certuser
FTP_PASS=ftppassword
FTP_PATH=certs
PFX_PASSWORD=supersecretpassword
```

### SonicWall Configuration
SonicWall deployments automatically use the centralized FTP server - no additional configuration needed per deployment.

### FortiGate Configuration
FortiGate deployments work with just the API key - no FTP server required.

## Status Tracking

The deployment status will show:
- **pending**: Deployment queued
- **success**: SSL VPN certificate deployed successfully
- **failed**: Deployment encountered an error

Detailed logs are stored in the deployment details and can be viewed in the browser console.

## Auto-Renewal

When auto-renewal is enabled:
1. System monitors certificate expiration dates
2. Automatically requests new certificates from Let's Encrypt
3. Deploys renewed certificates to all associated SSL VPN systems
4. Updates next renewal date

## Troubleshooting

### FortiGate Issues
- Verify API key has VPN certificate management permissions
- Check firewall connectivity and management port access
- Ensure certificate import quotas are not exceeded

### SonicWall Issues
- Verify centralized FTP server accessibility from SonicWall
- Check FTP credentials in environment variables
- Check admin credentials and CLI access
- Ensure sufficient storage space for certificate files
- Verify SonicOS version compatibility
- Check FTP_HOST, FTP_PORT, FTP_USER, and FTP_PASS in .env file

### General Issues
- Check certificate validity and format
- Verify target system configuration
- Review deployment logs for specific error details

## Technical Details

### Architecture
- **VPN Managers**: Specialized managers for FortiGate and SonicWall VPN operations
- **Factory Pattern**: Automatic manager selection based on target system type
- **Async Operations**: Non-blocking deployment with real-time status updates
- **Error Handling**: Comprehensive error reporting and rollback capabilities

### Security
- Private keys are encrypted at rest
- FTP credentials stored securely in deployment configuration
- API keys encrypted in target system settings
- Temporary files cleaned up automatically

### Integration Points
- Extends existing firewall manager architecture
- Reuses certificate storage and encryption systems
- Integrates with existing deployment workflow
- Compatible with auto-renewal infrastructure

## Next Steps

1. Test deployments with non-production systems first
2. Configure FTP settings for SonicWall systems
3. Set up auto-renewal for production certificates
4. Monitor deployment logs and status updates

For technical support or feature requests, refer to the system logs and deployment details.