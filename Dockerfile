# Use an official Python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /mmogame

# Copy source code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port Flask will run on
EXPOSE 8116


RUN pip install --no-cache-dir gunicorn

# Run the Flask app using flask_socketio
CMD ["gunicorn", "-k", "geventwebsocket.gunicorn.workers.GeventWebSocketWorker", "-w", "1", "server:app", "--bind", "0.0.0.0:8116"]
