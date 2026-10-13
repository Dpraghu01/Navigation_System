# Indoor Building Navigation System

A full-stack software solution designed to parse Industry Foundation Classes (IFC) architectural models, automatically generate navigational graphs, and visualize the quickest path between any two rooms in a 3D environment. 

The application utilizes an exploded-axonometric 3D view to separate floors visually, providing a clear, interactive spatial layout for end-users, complete with user authentication and dynamic shortest-path routing.

## 🛠 Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Frontend Visualization** | Three.js | Renders 3D building geometry, exploded floors, and route animations. |
| **Frontend Framework** | Vanilla JS + Vite | Handles UI logic, state management, and local development proxying. |
| **Backend API** | Python + Flask | Serves graph data, processes user authentication, and executes routing requests. |
| **Database** | SQLite + SQLAlchemy | Lightweight database for managing user registration and login credentials. |
| **Graph Processing** | ifcopenshell + Python | Extracts spatial bounding boxes, nodes, and valid edges from `.ifc` files. |
| **Routing Algorithm** | Dijkstra (`heapq`) | Calculates the shortest distance path across floors and stairwells. |

## 📁 Project Structure

```text
indoor-navigation/
├── backend/
│   ├── app.py                   # Flask API entry point (Port 5001)
│   ├── models.py                # SQLAlchemy DB models for users
│   ├── pathfinder.py            # Dijkstra graph traversal logic
│   ├── extract_nodes_V2.py      # IFC parsing and JSON graph extraction
│   ├── requirements.txt         # Python dependencies
│   └── data/
│       └── sample_building.ifc  # Source 3D architectural model
│
└── frontend/
    ├── index.html               # Main 3D navigation interface
    ├── landing.html             # User registration and login portal
    ├── package.json             # NPM dependencies
    ├── vite.config.js           # Vite dev server and proxy configuration
    └── src/
        ├── main.js              # Three.js application bootstrapper
        ├── landing.js           # Authentication logic
        └── style.css            # UI styling
```
Installation & Setup
1. Backend Environment Setup
Navigate to the backend directory, initialize a virtual environment, and install the necessary Python packages.

Bash
cd backend
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install Flask Flask-SQLAlchemy Flask-CORS werkzeug numpy ifcopenshell
2. Extract the Building Graph
Before running the API, you must parse the raw .ifc model to generate the building_graph.json file. This file contains the spatial nodes, room boundaries, and connectivity edges required by the frontend and the routing algorithm.

```Bash
# Ensure you are still in the backend directory and the venv is active
python extract_nodes_V2.py data/sample_building.ifc
```

Note: A successful extraction will generate building_graph.json in the backend directory.

3. Frontend Setup
Open a new terminal window, navigate to the frontend directory, and install the Node.js dependencies.

```Bash
cd frontend
npm install
```
🏃‍♂️ Running the Application
You must run both the backend API and the frontend development server simultaneously.


Terminal 1: Start the Flask Backend

```Bash
cd backend
source venv/bin/activate
python app.py
```
The API will boot on http://localhost:5001. The SQLite database (navigation.db) will be automatically created on the first run.

Terminal 2: Start the Vite Frontend

```Bash
cd frontend
npm run dev
```
Vite will boot on http://localhost:3000.

🧭 Usage Guidelines
Access the App: Open your browser and navigate to http://localhost:3000. You will be automatically redirected to the landing page.

Authenticate: Register a new user account (or log in if you already have one).

Navigate: Once redirected to the main 3D interface:

Select a Starting Room and a Destination Room from the dropdown menus.

Click Calculate Route.

The camera will display the glowing path traversing the 3D space, showing stairwell transitions and total distance.

View Modes: Toggle between 3D Exploded (default isometric view) and 2D Top-Down for different spatial perspectives.

Session Management: Click the user icon in the top right corner to log out.