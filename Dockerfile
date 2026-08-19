FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY run.py .

# Create runtime directories
RUN mkdir -p data/bin logs

# Expose web UI port
EXPOSE 8080

# Start the application
CMD ["python", "run.py"]
