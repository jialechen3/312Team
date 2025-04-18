from flask import Flask, render_template
from flask_socketio import SocketIO, send
from pymongo import MongoClient
import eventlet
eventlet.monkey_patch()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production
socketio = SocketIO(app)
mongo_client = MongoClient("mongodb://mongo:27017/")
db = mongo_client["mmo_game"]
users_collection = db["users"]

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/api/hello')
def hello():
    return 'Hello from the MMO backend!'

@socketio.on('message')
def handle_message(msg):
    print(f"Received message: {msg}")
    send(f"Server received: {msg}", broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)