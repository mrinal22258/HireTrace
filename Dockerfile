# HireTrace Production Container
FROM python:3.12-slim

# System dependencies for PDF/Docx text parsing and FAISS
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create uploads directory and ensure permissions
RUN mkdir -p uploads benchmarks eval_cases/custom_uploads

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

# Start HireTrace application server
CMD ["python", "ui/server.py", "--port", "8000", "--host", "0.0.0.0"]
