

from flask import Flask, render_template
from flask_socketio import SocketIO, send
from util.auth import auth_bp
from util.database import user_collection

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Replace with a secure key in production
socketio = SocketIO(app, async_mode='threading')


app.register_blueprint(auth_bp)
@app.route('/')
def index():
    user_collection.insert_one({"name": "Jiale Test"})
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