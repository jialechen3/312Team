# Use an official Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy source code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port Flask will run on
EXPOSE 8080

# Run the Flask app using flask_socketio
CMD ["python", "app.py"]