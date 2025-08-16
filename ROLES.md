# CertSync Role-Based Access Control (RBAC)

## Role Definitions

### Admin
**Full system access** - Can do everything technicians can do PLUS:
- Add new users
- Delete existing users  
- View all users
- Change other users' passwords
- Modify system settings (logging levels, etc.)

### Technician
**Operational access** - Can perform all certificate and firewall operations:
- Manage firewalls (create, read, update, delete)
- Test firewall connections
- Manage DNS provider accounts  
- Manage hostnames
- Request and manage certificates
- View system logs
- Change their own password only

### Readonly
**View-only access** - Limited to viewing data:
- View dashboard statistics
- View existing hostnames
- View certificates (but cannot request new ones)
- View system logs
- Change their own password only

## Implementation Notes

**Key Principle**: The ONLY differences between Admin and Technician roles should be user management functions. Everything else (firewalls, certificates, DNS, hostnames) should be accessible to both Admin and Technician users.

**Current Role Validation Patterns**:
- `require_role('admin')` - Admin only (user management, critical system settings)
- `require_admin_or_technician()` - Operational tasks (firewalls, certificates, DNS)
- `require_any_authenticated()` - View-only tasks (dashboard, logs)

**Endpoints by Role**:

### Admin Only
- POST `/auth/users/` (create user)
- DELETE `/auth/users/{user_id}` (delete user)
- GET `/auth/users/` (list all users) 
- PUT `/auth/users/{user_id}/password` (change other user's password)
- POST `/system/log-level/` (change system logging level)

### Admin OR Technician
- POST `/firewalls/` (create firewall)
- GET `/firewalls/` (list firewalls)
- GET `/firewalls/{firewall_id}` (read firewall)
- PUT `/firewalls/{firewall_id}` (update firewall)
- DELETE `/firewalls/{firewall_id}` (delete firewall)
- GET `/firewalls/test_connection_sse/*` (test firewall connections)
- All certificate endpoints (request, manage, deploy)
- All DNS provider account endpoints
- All hostname endpoints
- GET `/system/log-level/` (view logging level)

### Any Authenticated User (Admin, Technician, Readonly)
- PUT `/auth/users/me/password` (change own password)
- GET `/system/stats/` (dashboard statistics)  
- GET `/logs/` (view logs)
- Dashboard and read-only views

## Future AI Reference

When implementing new features or endpoints, follow this role hierarchy:
1. **User management functions** → Admin only
2. **Operational tasks** (CRUD operations, testing, configuration) → Admin OR Technician  
3. **Read-only views** → Any authenticated user

This ensures consistent access control across the entire application.
