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

BUILDINGS = {
    "campus_main": "building_graph.json",
    "science_block": "building_graph_b.json"
}

GRAPH_CACHE = {}

def get_graph(building_id):
    if building_id not in BUILDINGS:
        raise ValueError("Building not found")
        
    if building_id not in GRAPH_CACHE:
        filepath = os.path.join(os.path.dirname(__file__), BUILDINGS[building_id])
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Missing {filepath}")
        GRAPH_CACHE[building_id] = load_graph(filepath)
    return GRAPH_CACHE[building_id]

@app.route("/api/buildings", methods=["GET"])
def list_buildings():
    """Returns available buildings for the frontend dropdown."""
    return jsonify([
        {"id": "campus_main", "name": "Main Campus Building"},
        {"id": "science_block", "name": "Science & Engineering Block"}
    ]), 200

@app.route("/api/building/<building_id>", methods=["GET"])
def get_building_data(building_id):
    try:
        graph = get_graph(building_id)
        client_payload = {}
        
        for floor_name, floor_data in graph.items():
            if floor_name == "stair_connections":
                client_payload[floor_name] = floor_data
                continue
                
            client_payload[floor_name] = {
                "elevation": floor_data.get("elevation", 0),
                "shoeboxes": floor_data.get("shoeboxes", []),
                # FIX: Send ONLY the stair nodes to the frontend
                "nodes": [n for n in floor_data.get("nodes", []) if n.get("type") == "stair"]
            }
        return jsonify(client_payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/navigate", methods=["POST"])
def navigate():
    body = request.get_json() or {}
    building_id = body.get("building_id")
    start_room = body.get("start")
    end_room = body.get("end")

    if not all([building_id, start_room, end_room]):
        return jsonify({"error": "Building ID, start, and end rooms are required"}), 400

    filepath = os.path.join(os.path.dirname(__file__), BUILDINGS.get(building_id, ""))
    if not os.path.exists(filepath):
         return jsonify({"error": "Invalid building"}), 404

    cost, path = find_shortest_path(start_room, end_room, json_path=filepath)

    if path is None:
        return jsonify({"success": False, "message": "No valid path found"}), 404

    return jsonify({
        "success": True,
        "start": start_room, # FIX: Added back to enable green source color
        "end": end_room,     # FIX: Added back to enable red destination color
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