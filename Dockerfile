# Start from official Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy all backend code
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the FastAPI port
EXPOSE 3001

# Run the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"]

