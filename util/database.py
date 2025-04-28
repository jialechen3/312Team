import os
from pymongo import MongoClient

# Check if running inside Docker
docker_db = os.environ.get('DOCKER_DB', "false").lower() == "true"

# Set up MongoDB connection string
mongo_client = MongoClient("mongodb://mongo:27017")  # docker-compose service name


# Access the database and collections
db = mongo_client["mmo_game"]
user_collection = db["users"]
chat_collection = db["chat"]
room_collection = db["rooms"]