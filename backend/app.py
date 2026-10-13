import os
import json
from flask import Flask, jsonify, request, session
from flask_cors import CORS
from pathfinder import find_shortest_path, load_graph

from models import db, User  # Import the new DB and Model




app = Flask(__name__)
CORS(app)  # Allows Vite dev server requests

# Database & Session Configuration
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///navigation.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Automatically create the SQLite file and tables if they don't exist
with app.app_context():
    db.create_all()

GRAPH_FILE = os.path.join(os.path.dirname(__file__), "building_graph.json")

# In-memory graph cache to prevent repeated disk I/O on every query
GRAPH_CACHE = None

def get_graph():
    global GRAPH_CACHE
    if GRAPH_CACHE is None:
        if not os.path.exists(GRAPH_FILE):
            raise FileNotFoundError(f"Missing {GRAPH_FILE}. Run extract_nodes_V2.py first.")
        GRAPH_CACHE = load_graph(GRAPH_FILE)
    return GRAPH_CACHE

@app.route("/api/building", methods=["GET"])
def get_building_data():
    """Returns the full building layout and extracted graph for 3D rendering."""
    try:
        data = get_graph()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/rooms", methods=["GET"])
def get_rooms():
    """Extracts and returns a sorted list of unique room names across all floors."""
    try:
        data = get_graph()
        rooms = set()
        for floor_name, floor_data in data.items():
            if floor_name == "stair_connections":
                continue
            for box in floor_data.get("shoeboxes", []):
                name = box.get("name")
                if name:
                    rooms.add(name)
        return jsonify(sorted(list(rooms))), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/navigate", methods=["POST"])
def navigate():
    """
    Accepts start and end room names, executes Dijkstra's algorithm,
    and returns the computed path and total distance.
    """
    body = request.get_json() or {}
    start_room = body.get("start")
    end_room = body.get("end")

    if not start_room or not end_room:
        return jsonify({"error": "Both 'start' and 'end' rooms are required"}), 400

    cost, path = find_shortest_path(start_room, end_room, json_path=GRAPH_FILE)

    if path is None:
        return jsonify({
            "success": False,
            "message": f"No valid path found between {start_room} and {end_room}"
        }), 404

    return jsonify({
        "success": True,
        "start": start_room,
        "end": end_room,
        "total_distance": round(cost, 2),
        "path": [{"floor": floor, "pos": list(pos)} for floor, pos in path]
    }), 200

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username already exists"}), 400

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    session["user_id"] = new_user.id
    session["username"] = new_user.username
    return jsonify({"success": True, "username": new_user.username}), 200

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        session["user_id"] = user.id
        session["username"] = user.username
        return jsonify({"success": True, "username": user.username}), 200

    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/api/me", methods=["GET"])
def me():
    """Checks if the user is currently logged in via session cookie."""
    if "user_id" in session:
        return jsonify({"success": True, "username": session.get("username")}), 200
    return jsonify({"success": False, "message": "Not authenticated"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True}), 200



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)