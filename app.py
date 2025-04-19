from flask import Flask, render_template
from flask_socketio import SocketIO, send
from flask import request, redirect, make_response, jsonify
from util.auth import validate_password  
from pymongo import MongoClient
import uuid
import bcrypt
import hashlib
import eventlet
eventlet.monkey_patch()
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production
socketio = SocketIO(app)

mongo_client = MongoClient("mongodb://mongo:27017/")
db = mongo_client["mmo_game"]
user_collection = db["users"]
authToken_collection = db["auth_tokens"]
chat_collection = db["chat"] 

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/api/hello')
def hello():
    return 'Hello from the MMO backend!'

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    data = request.form  # or request.get_json() if using JSON body
    user = data.get('username')
    password = data.get('password')

    if not user or not password:
        return "Missing credentials", 400

    dbEntry = user_collection.find_one({'username': user})
    if not dbEntry:
        return "Incorrect username", 400

    if not bcrypt.checkpw(password.encode(), dbEntry["password"].encode()):
        return "Incorrect password", 400

    auth_token = str(uuid.uuid4())
    hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
    authToken_collection.insert_one({"username": user, "auth_token": hashed_token})

    resp = make_response("Successful Log In")
    resp.set_cookie("auth_token", auth_token, httponly=True, max_age=3600)
    return resp

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    data = request.form
    user = data.get('username')
    password = data.get('password')

    if not user or not password:
        return "Missing credentials", 400

    if not validate_password(password):  # define this as needed
        return "Bad password", 400

    if user_collection.find_one({"username": user}):
        return "Username already taken", 400

    hashed_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())

    user_collection.insert_one({
        "id": user_id,
        "username": user,
        "password": hashed_pw
    })

    resp = make_response("Registered successfully")
    resp.set_cookie("session", user_id)
    return resp

@app.route('/logout', methods=['POST'])
def logout():
    auth_token = request.cookies.get("auth_token")
    if auth_token:
        hashed_token = hashlib.sha256(auth_token.encode()).hexdigest()
        authToken_collection.delete_one({"auth_token": hashed_token})

    resp = make_response("Logged out")
    resp.set_cookie("auth_token", '', expires=0)
    return resp


@socketio.on('message')
def handle_message(msg):
    print(f"Received message: {msg}")
    send(f"Server received: {msg}", broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080)