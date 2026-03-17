# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# 1. Install System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Copy requirements
COPY requirements.txt .

# 3. Install Python dependencies
RUN pip install --no-cache-dir GDAL==$(gdal-config --version | awk -F'[.]' '{print $1"."$2}')
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy Code
COPY backend/main.py ./backend/main.py
COPY frontend/app.py ./frontend/app.py
COPY rf_crop_recommendation_model.pkl .

# 5. Expose ports
EXPOSE 8000
EXPOSE 8501

# 6. Startup Script
RUN echo '#!/bin/bash\n\
echo "Starting FastAPI Backend..."\n\
uvicorn backend.main:app --host 0.0.0.0 --port 8000 & \n\
echo "Starting Streamlit Frontend..."\n\
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 \n\
' > /app/start.sh && chmod +x /app/start.sh

# Run the startup script
CMD ["/app/start.sh"]