import sys
import json
import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import numpy as np
from node_sol_v1 import Node, get_valid_edges

def get_element_position(element, scale):
    try:
        matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
        return (
            round(float(matrix[0][3]) * scale, 2),
            round(float(matrix[1][3]) * scale, 2),
            round(float(matrix[2][3]) * scale, 2)
        )
    except Exception:
        return None

def get_space_shoebox(space, scale):
    pos = get_element_position(space, scale)
    if pos:
        return {
            "name": space.Name or space.LongName or "Room",
            "min": [round(pos[0] - 0.8, 2), round(pos[1] - 0.8, 2), round(pos[2], 2)],
            "max": [round(pos[0] + 0.8, 2), round(pos[1] + 0.8, 2), round(pos[2] + 2.4, 2)],
            "center": [round(pos[0], 2), round(pos[1], 2)]
        }
    return None

def generate_v2_sparse_nodes(shoeboxes, n=1.0):
    if not shoeboxes:
        return []

    # Calculate the Minimum Bounding Rectangle (MBR) of all rooms + 1 unit padding
    min_x = min(box["min"][0] for box in shoeboxes) - 1.0
    min_y = min(box["min"][1] for box in shoeboxes) - 1.0
    max_x = max(box["max"][0] for box in shoeboxes) + 1.0
    max_y = max(box["max"][1] for box in shoeboxes) + 1.0
    
    g_x, g_y = min_x, min_y
    g_w = max_x - min_x
    g_h = max_y - min_y

    restricted_zones = [
        (box["min"][0], box["min"][1], 
         box["max"][0] - box["min"][0], 
         box["max"][1] - box["min"][1])
        for box in shoeboxes
    ]

    walk_nodes = []
    
    # Generate the nxn grid and extract free-space centroids
    for i in range(int(np.ceil(g_w / n))):
        for j in range(int(np.ceil(g_h / n))):
            sq_x = g_x + (i * n)
            sq_y = g_y + (j * n)

            if sq_x + n > g_x + g_w or sq_y + n > g_y + g_h:
                continue

            intersects_restricted = False
            for z_x, z_y, z_w, z_h in restricted_zones:
                if (sq_x + n > z_x and sq_x < z_x + z_w and
                    sq_y + n > z_y and sq_y < z_y + z_h):
                    intersects_restricted = True
                    break
            
            if not intersects_restricted:
                c_x = round(sq_x + n / 2.0, 2)
                c_y = round(sq_y + n / 2.0, 2)
                walk_nodes.append(Node((c_x, c_y), "walk"))
                
    return walk_nodes

def process_ifc_graph(ifc_path):
    model = ifcopenshell.open(ifc_path)
    scale = ifcopenshell.util.unit.calculate_unit_scale(model)
    storeys = model.by_type("IfcBuildingStorey")

    floor_graphs = {}
    for storey in storeys:
        elev_raw = getattr(storey, 'Elevation', 0.0) or 0.0
        elevation = round(float(elev_raw) * scale, 2)
        floor_graphs[storey.Name] = {
            "elevation": elevation,
            "doors_raw": [],
            "shoeboxes": [],
            "stair_nodes": [],
            "unique_positions": set(),
        }

    def get_matching_floor(z_coord):
        closest_floor, min_diff = None, float("inf")
        for floor_name, data in floor_graphs.items():
            diff = abs(data["elevation"] - z_coord)
            if diff < 5.0:  
                if diff < min_diff:
                    min_diff = diff
                    closest_floor = floor_name
        if not closest_floor and floor_graphs:
            closest_floor = min(floor_graphs.keys(), key=lambda f: abs(floor_graphs[f]["elevation"] - z_coord))
        return closest_floor

    for space in model.by_type("IfcSpace"):
        box = get_space_shoebox(space, scale)
        if box:
            floor = get_matching_floor(box["min"][2])
            if floor:
                floor_graphs[floor]["shoeboxes"].append(box)

    for door in model.by_type("IfcDoor"):
        pos = get_element_position(door, scale)
        if pos:
            floor = get_matching_floor(pos[2])
            if floor:
                floor_graphs[floor]["doors_raw"].append(pos)

    json_output = {}
    raw_stair_map = {}

    for floor_name, data in floor_graphs.items():
        if not data["shoeboxes"]:
            continue

        min_z = min(box["min"][2] for box in data["shoeboxes"])
        data["elevation"] = min_z
        
        door_nodes = []
        for box in data["shoeboxes"]:
            x_min, x_max = box["min"][0], box["max"][0]
            y_min, y_max = box["min"][1], box["max"][1]
            room_has_door = False
            
            for d_pos in data["doors_raw"]:
                dx, dy = d_pos[0], d_pos[1]
                on_x = (abs(dx - x_min) < 0.8 or abs(dx - x_max) < 0.8) and (y_min - 0.2 <= dy <= y_max + 0.2)
                on_y = (abs(dy - y_min) < 0.8 or abs(dy - y_max) < 0.8) and (x_min - 0.2 <= dx <= x_max + 0.2)
                
                if on_x or on_y:
                    room_has_door = True
                    snap_pos = (x_min, dy) if abs(dx - x_min) < abs(dx - x_max) else (x_max, dy)
                    xy_pos = (round(snap_pos[0], 2), round(snap_pos[1], 2))
                    if xy_pos not in data["unique_positions"]:
                        data["unique_positions"].add(xy_pos)
                        door_nodes.append(Node(xy_pos, "door"))
            
            if not room_has_door:
                synth_pos = (x_min, round((y_min + y_max) / 2, 2))
                xy_pos = (round(synth_pos[0], 2), round(synth_pos[1], 2))
                if xy_pos not in data["unique_positions"]:
                    data["unique_positions"].add(xy_pos)
                    door_nodes.append(Node(xy_pos, "door"))

        stair_x = data["shoeboxes"][0]["max"][0] + 1.0
        stair_y = data["shoeboxes"][0]["max"][1] + 1.0
        data["stair_nodes"] = [Node((stair_x, stair_y), "stair")]
        if data["stair_nodes"]:
            raw_stair_map[floor_name] = data["stair_nodes"][0]

        walk_nodes = generate_v2_sparse_nodes(data["shoeboxes"], n=1.0)
        all_floor_nodes = walk_nodes + door_nodes + data["stair_nodes"]
        
        rectangles = [
            (b["min"][0], b["min"][1], b["max"][0], b["max"][1]) 
            for b in data["shoeboxes"] 
            if not any(kw in b["name"].lower() for kw in ["flur", "corridor", "hall", "passage", "stair"])
        ]

        valid_edges = get_valid_edges(all_floor_nodes, rectangles)
        clean_edges = [e for e in valid_edges if 0.1 < e[2] <= 1.5]

        json_output[floor_name] = {
            "elevation": data["elevation"],
            "shoeboxes": data["shoeboxes"],
            "nodes": [{"pos": n.pos, "type": n.node_type} for n in all_floor_nodes],
            "edges": [{"from": e[0].pos, "to": e[1].pos, "distance": e[2]} for e in clean_edges],
        }

    sorted_floors = sorted([f for f in json_output.keys() if f in raw_stair_map], key=lambda f: json_output[f]["elevation"])
    stair_connections = []
    for i in range(len(sorted_floors) - 1):
        f1, f2 = sorted_floors[i], sorted_floors[i+1]
        vert_dist = abs(json_output[f2]["elevation"] - json_output[f1]["elevation"])
        stair_connections.append({
            "from_floor": f1,
            "from_pos": raw_stair_map[f1].pos,
            "to_floor": f2,
            "to_pos": raw_stair_map[f2].pos,
            "distance": round(vert_dist, 2)
        })

    if stair_connections:
        json_output["stair_connections"] = stair_connections

    with open("building_graph.json", "w") as f:
        json.dump(json_output, f, indent=4)
        
    print(f"Successfully processed {ifc_path} with unit scale multiplier: {scale}")

if __name__ == "__main__":
    file_to_process = sys.argv[1] if len(sys.argv) > 1 else "sample_building.ifc"
    process_ifc_graph(file_to_process)