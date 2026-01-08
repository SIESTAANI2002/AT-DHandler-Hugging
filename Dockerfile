# Python 3.10 Base Image
FROM python:3.9-slim-bookworm

# Working Directory
WORKDIR /app

# Install Essential System Dependencies
# (Git and GCC needed for some python libraries)
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Requirements and Install
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy Project Files
COPY . .

# Permission for Script
RUN chmod +x run.sh

# Start Command
CMD ["bash", "run.sh"]
