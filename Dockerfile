FROM python:3.11-slim

WORKDIR /workspace

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Start application server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
