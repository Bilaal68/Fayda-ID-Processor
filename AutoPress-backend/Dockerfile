FROM python:3.13-slim

WORKDIR /app

# System dependencies for PDF/image processing
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY . .

# Render/Hugging Face will provide the PORT
EXPOSE 7860

# Start Flask with Gunicorn
CMD ["sh", "-c", "gunicorn --timeout 360 --workers 1 --threads 4 --bind 0.0.0.0:${PORT:-7860} app:app"]
