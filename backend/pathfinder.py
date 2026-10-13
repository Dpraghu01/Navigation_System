import json
import heapq
import sys

def load_graph(json_path="building_graph.json"):
    with open(json_path, "r") as f:
        return json.load(f)

def get_room_door(graph_data, room_name):
    for floor_name, floor_data in graph_data.items():
        if floor_name == "stair_connections":
            continue
        for box in floor_data.get("shoeboxes", []):
            if box["name"].lower() == room_name.lower():
                x_min, x_max = box["min"][0], box["max"][0]
                y_min, y_max = box["min"][1], box["max"][1]
                
                for node in floor_data["nodes"]:
                    nx, ny = node["pos"]
                    on_boundary = (
                        (abs(nx - x_min) < 0.1 or abs(nx - x_max) < 0.1) and (y_min <= ny <= y_max)
                    ) or (
                        (abs(ny - y_min) < 0.1 or abs(ny - y_max) < 0.1) and (x_min <= nx <= x_max)
                    )
                    if on_boundary:
                        return floor_name, tuple(node["pos"])
                
                cx, cy = box["center"]
                best_door, min_dist = None, float("inf")
                for node in floor_data["nodes"]:
                    if node["type"] == "door":
                        dist = ((node["pos"][0] - cx)**2 + (node["pos"][1] - cy)**2)**0.5
                        if dist < min_dist:
                            min_dist = dist
                            best_door = (floor_name, tuple(node["pos"]))
                return best_door
    return None, None

def find_shortest_path(start_room, end_room, json_path="building_graph.json"):
    data = load_graph(json_path)
    
    start_floor, start_pos = get_room_door(data, start_room)
    end_floor, end_pos = get_room_door(data, end_room)
    
    if not start_pos or not end_pos:
        print(f"Could not find room doors for: {start_room} -> {end_room}")
        return None, None

    adj = {}
    def add_edge(u, v, weight):
        adj.setdefault(u, []).append((v, weight))
        adj.setdefault(v, []).append((u, weight))

    for floor_name, floor_data in data.items():
        if floor_name == "stair_connections":
            continue
        for node in floor_data["nodes"]:
            adj.setdefault((floor_name, tuple(node["pos"])), [])
        for edge in floor_data["edges"]:
            add_edge((floor_name, tuple(edge["from"])), (floor_name, tuple(edge["to"])), edge["distance"])

    for conn in data.get("stair_connections", []):
        add_edge((conn["from_floor"], tuple(conn["from_pos"])), (conn["to_floor"], tuple(conn["to_pos"])), conn["distance"])

    start_node = (start_floor, start_pos)
    end_node = (end_floor, end_pos)

    pq = [(0, start_node, [start_node])]
    visited = set()
    
    while pq:
        cost, curr, path = heapq.heappop(pq)
        if curr in visited:
            continue
        visited.add(curr)
        
        if curr == end_node:
            return cost, path
            
        for neighbor, weight in adj.get(curr, []):
            if neighbor not in visited:
                heapq.heappush(pq, (cost + weight, neighbor, path + [neighbor]))
                
    return None, None

if __name__ == "__main__":
    room_a = sys.argv[1] if len(sys.argv) > 1 else "A101"
    room_b = sys.argv[2] if len(sys.argv) > 2 else "A203"
    
    cost, path = find_shortest_path(room_a, room_b)
    if path:
        print(f"Shortest path from {room_a} to {room_b} ({cost:.2f}m):")
        for floor, pos in path:
            print(f"  [{floor}] -> {pos}")
            
        output = {
            "start": room_a,
            "end": room_b,
            "total_distance": round(cost, 2),
            "path": [{"floor": f, "pos": list(p)} for f, p in path]
        }
        with open("path_result.json", "w") as f:
            json.dump(output, f, indent=4)
        print("Path saved to path_result.json successfully!")
    else:
        print(f"No valid path found between {room_a} and {room_b}.")