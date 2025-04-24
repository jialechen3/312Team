import re

from flask import Flask, render_template, Blueprint, redirect, jsonify
from flask import request, g
from flask import request,make_response
import uuid
import bcrypt
import hashlib
from util.database import user_collection
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
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
        "password": hashed_pw,
        "auth_token": None       # placeholder for session token
    })

    resp = make_response(redirect("/"))
    resp.set_cookie("session", user_id)
    return resp

@auth_bp.route('/login', methods=['GET', 'POST'])
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
        return render_template("login.html", error="Incorrect username")

    if not bcrypt.checkpw(password.encode(), dbEntry["password"].encode()):
        return render_template("login.html", error="Incorrect password")

    token = str(uuid.uuid4())

    hashed = hash_token(token)
    user_collection.update_one({"username": user}, {"$set": {"auth_token": hashed}})

    resp = make_response(redirect("/lobby"))
    resp.set_cookie("auth_token", token, httponly=True, max_age=3600)
    return resp

@auth_bp.route('/logout', methods=['POST'])
def logout():
    token = request.cookies.get("auth_token")

    if token :
        user_collection.update_one({"auth_token": hash_token(token)}, {"$unset" : {"auth_token": ""}})


    resp = make_response(redirect("/"))
    resp.set_cookie("auth_token", '', expires=0)
    return resp


def validate_password(string):
    if len(string) < 8:
        return False
    if not re.search(r'[a-z]', string): return False
    if not re.search(r'[A-Z]', string): return False
    if not re.search(r'\d', string): return False
    if not re.search(r'[!@#$%^&()\-_=]', string): return False
    if not re.fullmatch(r'[A-Za-z0-9!@#$%^&()\-_=]+', string): return False
    return True

# hash auth token for DB storage
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@auth_bp.before_app_request
def load_CurrentUser():

    token = request.cookies.get("auth_token")
    if token:
        g.user = user_collection.find_one({"auth_token": hash_token(token)})
    else:
        g.user = None


@auth_bp.route('/api/whoami')
def whoami():
    token = request.cookies.get("auth_token")
    if not token:
        return jsonify({"username": None})

    user = user_collection.find_one({"auth_token": hash_token(token)})
    if user:
        return jsonify({"username": user["username"]})

    return jsonify({"username": None})

