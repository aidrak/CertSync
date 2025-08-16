# CertSync - Multi-Firewall Certificate Management System

CertSync is an open-source, web-based certificate management system designed for Managed Service Providers (MSPs) to automate the lifecycle of SSL certificates on multi-vendor firewall environments.

## Features

- **Multi-Vendor Firewall Support**: Manage certificates on FortiGate, Palo Alto Networks, and SonicWall firewalls.
- **Automated Certificate Renewal**: Integrates with Let's Encrypt for automated certificate issuance and renewal.
- **Flexible DNS-01 Challenge**: Supports Cloudflare, Amazon Route 53, and GoDaddy for DNS-01 validation.
- **Secure Credential Storage**: Encrypts all sensitive credentials at rest.
- **Web-Based Dashboard**: A simple, intuitive web interface for managing firewalls and certificates.
- **Automated Renewals**: A background worker automatically renews and deploys certificates before they expire.
- **Containerized Deployment**: Easily deploy the entire application using Docker and Docker Compose.

## Getting Started

### Prerequisites

- Docker
- Docker Compose

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd certsync
    ```

2.  **Configure the application:**
    -   Copy the `.env.example` file to `.env`:
        ```bash
        cp .env.example .env
        ```
    -   Edit the `.env` file and provide the necessary configuration values, including your database credentials, Let's Encrypt email, and a secure `ENCRYPTION_KEY`. You can generate an encryption key with:
        ```bash
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        ```

3.  **Build and run the application:**
    ```bash
    docker-compose up -d --build
    ```

4.  **Access the application:**
-   The backend API will be available at `http://localhost:8233`.
    -   The frontend dashboard can be accessed by opening the `frontend/src/index.html` file in your web browser.

## API Documentation

The backend is a FastAPI application, which means it provides automatic interactive API documentation. You can access it at:

-   **Swagger UI**: `http://localhost:8233/docs`
-   **ReDoc**: `http://localhost:8233/redoc`

### Main Endpoints

-   `POST /firewalls/`: Add a new firewall.
-   `GET /firewalls/`: Get a list of all firewalls.
-   `POST /certificates/request-le-cert`: Request a new certificate from Let's Encrypt.
-   `POST /certificates/deploy`: Deploy a certificate to one or more firewalls.
-   `GET /certificates/`: Get a list of all certificates.

## Running Tests

To run the backend tests, execute the following command:

```bash
docker exec certsync-cert-manager-1 pytest
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue.

## License

This project is licensed under the MIT License.
