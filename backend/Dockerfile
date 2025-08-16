# backend/Dockerfile (Corrected syntax)

# Start with an official Python runtime as a parent image
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# Combine all apt-get and cleanup commands on one line to avoid line continuation issues
RUN apt-get update && apt-get install -y gcc postgresql-client && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (this will include your entrypoint.sh)
COPY . .

# Correct line endings and make the entrypoint script executable
RUN sed -i 's/\r$//' /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose port
EXPOSE 8233

# Your entrypoint.sh will now be handled by docker-compose.yml
# This CMD line should be removed or commented out when using 'entrypoint' in docker-compose.yml
# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8233"]
