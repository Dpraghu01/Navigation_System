import sys
import json
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.unit
from node_sol_v1 import Node, get_valid_edges

# Keywords used to tell circulation spaces (corridors/halls) apart from
# enclosed rooms. Corridors are treated as *walkable free area*, not as
# obstacles that block the pathfinding mesh.
CORRIDOR_KEYWORDS = ["flur", "corridor", "hall", "passage"]

# Geometry settings used to triangulate each element's real 3D shape in
# world coordinates. This is what lets us read an element's *actual*
# bounding box / profile dimensions instead of guessing them from a fixed
# offset around its insertion point.
_GEOM_SETTINGS = ifcopenshell.geom.settings()
try:
    _GEOM_SETTINGS.set(_GEOM_SETTINGS.USE_WORLD_COORDS, True)
except Exception:
    # Newer IfcOpenShell releases (0.7+) use string-keyed settings instead
    # of the enum constants used above.
    _GEOM_SETTINGS.set("use-world-coords", True)


def get_shape_bbox(element, scale):
    """
    Extracts the true, real-world axis-aligned bounding box of an IFC
    element by triangulating its actual geometric representation and
    taking the min/max extents of the resulting mesh vertices.

    This replaces any fixed-offset approach: the returned box reflects the
    element's real Length (X), Width (Y) and Height (Z), taken directly
    from its IFC geometry, regardless of the element's rotation or true
    footprint shape.
    """
    try:
        shape = ifcopenshell.geom.create_shape(_GEOM_SETTINGS, element)
        verts = shape.geometry.verts
        if not verts:
            return None
        xs = [verts[i] * scale for i in range(0, len(verts), 3)]
        ys = [verts[i] * scale for i in range(1, len(verts), 3)]
        zs = [verts[i] * scale for i in range(2, len(verts), 3)]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        zmin, zmax = min(zs), max(zs)
        return {
            "min": [round(xmin, 2), round(ymin, 2), round(zmin, 2)],
            "max": [round(xmax, 2), round(ymax, 2), round(zmax, 2)],
            "center": [round((xmin + xmax) / 2.0, 2), round((ymin + ymax) / 2.0, 2)],
            "length": round(xmax - xmin, 2),
            "width": round(ymax - ymin, 2),
            "height": round(zmax - zmin, 2),
        }
    except Exception:
        return None


def is_corridor_space(name):
    name = (name or "").lower()
    return any(kw in name for kw in CORRIDOR_KEYWORDS)


def get_space_shoebox(space, scale):
    """Real bounding box of an IfcSpace, taken directly from its geometry."""
    bbox = get_shape_bbox(space, scale)
    if not bbox:
        return None
    return {
        "name": space.Name or space.LongName or "Room",
        "min": bbox["min"],
        "max": bbox["max"],
        "center": bbox["center"],
        "length": bbox["length"],
        "width": bbox["width"],
        "height": bbox["height"],
    }


def door_adjacent_to_room(door_box, room_box):
    """
    Determines whether a door sits on one of a room's boundary walls, using
    the door's own real thickness as the matching tolerance rather than an
    arbitrary constant -- a 0.9m x 0.15m door gets a much tighter tolerance
    than a 1.2m x 0.3m one, because the tolerance comes from its own
    extracted geometry.
    """
    dx0, dy0 = door_box["min"][0], door_box["min"][1]
    dx1, dy1 = door_box["max"][0], door_box["max"][1]
    rx0, ry0 = room_box["min"][0], room_box["min"][1]
    rx1, ry1 = room_box["max"][0], room_box["max"][1]

    tolerance = max(0.05, min(dx1 - dx0, dy1 - dy0))
    dcx, dcy = door_box["center"][0], door_box["center"][1]

    on_x_wall = (abs(dcx - rx0) <= tolerance or abs(dcx - rx1) <= tolerance) and (ry0 - tolerance <= dcy <= ry1 + tolerance)
    on_y_wall = (abs(dcy - ry0) <= tolerance or abs(dcy - ry1) <= tolerance) and (rx0 - tolerance <= dcx <= rx1 + tolerance)
    return on_x_wall or on_y_wall


def decompose_free_area(floor_bounds, obstacle_boxes, min_rect_size=0.5):
    """
    Decomposes the walkable free area of a floor -- the floor's total
    bounding area minus the exact room/obstacle bounding boxes -- into a
    set of non-overlapping rectangles.

    Approach: build a rectilinear grid from every obstacle edge coordinate,
    mark each grid cell "free" or "occupied" by testing its center against
    every obstacle box, then merge horizontally-adjacent free cells within
    each row into larger rectangles.
    """
    fxmin, fymin, fxmax, fymax = floor_bounds
    obstacle_rects = [(b["min"][0], b["min"][1], b["max"][0], b["max"][1]) for b in obstacle_boxes]

    xs = {fxmin, fxmax}
    ys = {fymin, fymax}
    for rxmin, rymin, rxmax, rymax in obstacle_rects:
        xs.add(max(fxmin, min(fxmax, rxmin)))
        xs.add(max(fxmin, min(fxmax, rxmax)))
        ys.add(max(fymin, min(fymax, rymin)))
        ys.add(max(fymin, min(fymax, rymax)))
    xs = sorted(xs)
    ys = sorted(ys)

    rectangles = []
    for yi in range(len(ys) - 1):
        y0, y1 = ys[yi], ys[yi + 1]
        if y1 - y0 < 1e-6:
            continue

        row_cells = []
        for xi in range(len(xs) - 1):
            x0, x1 = xs[xi], xs[xi + 1]
            if x1 - x0 < 1e-6:
                continue
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            occupied = any(
                rxmin < cx < rxmax and rymin < cy < rymax
                for rxmin, rymin, rxmax, rymax in obstacle_rects
            )
            if not occupied:
                row_cells.append([x0, x1])

        merged = []
        for x0, x1 in row_cells:
            if merged and abs(merged[-1][1] - x0) < 1e-6:
                merged[-1][1] = x1
            else:
                merged.append([x0, x1])

        for x0, x1 in merged:
            if (x1 - x0) >= min_rect_size and (y1 - y0) >= min_rect_size:
                rectangles.append((x0, y0, x1, y1))

    return rectangles


def walk_nodes_from_free_area(floor_bounds, obstacle_boxes):
    """Free-area decomposition path: one 'walk' node per free rectangle centroid."""
    nodes = []
    for x0, y0, x1, y1 in decompose_free_area(floor_bounds, obstacle_boxes):
        pos = (round((x0 + x1) / 2.0, 2), round((y0 + y1) / 2.0, 2))
        if not any(n.pos == pos for n in nodes):
            nodes.append(Node(pos, "walk"))
    return nodes


def walk_nodes_from_corridors(corridor_boxes):
    """
    When explicit corridor/hall IfcSpace entities exist, use their exact
    bounding boxes directly as the walkable free-area rectangles instead of
    running the grid decomposition.
    """
    nodes = []
    for box in corridor_boxes:
        pos = (round(box["center"][0], 2), round(box["center"][1], 2))
        if not any(n.pos == pos for n in nodes):
            nodes.append(Node(pos, "walk"))
    return nodes


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
            "stair_boxes": [],
            "unique_positions": set(),
        }

    def get_matching_floor(z_coord):
        closest_floor, min_diff = None, float("inf")
        for floor_name, data in floor_graphs.items():
            diff = abs(data["elevation"] - z_coord)
            if diff < 5.0:  # Relaxed tolerance for multi-scale models
                if diff < min_diff:
                    min_diff = diff
                    closest_floor = floor_name
        if not closest_floor and floor_graphs:
            closest_floor = min(floor_graphs.keys(), key=lambda f: abs(floor_graphs[f]["elevation"] - z_coord))
        return closest_floor

    # --- Step 1: exact bounding boxes for spaces, doors and stairs -------
    for space in model.by_type("IfcSpace"):
        box = get_space_shoebox(space, scale)
        if box:
            floor = get_matching_floor(box["min"][2])
            if floor:
                floor_graphs[floor]["shoeboxes"].append(box)

    for door in model.by_type("IfcDoor"):
        box = get_shape_bbox(door, scale)
        if box:
            floor = get_matching_floor(box["min"][2])
            if floor:
                floor_graphs[floor]["doors_raw"].append(box)

    for stair in model.by_type("IfcStair"):
        box = get_shape_bbox(stair, scale)
        if box:
            floor = get_matching_floor(box["min"][2])
            if floor:
                floor_graphs[floor]["stair_boxes"].append(box)

    json_output = {}
    raw_stair_map = {}

    for floor_name, data in floor_graphs.items():
        if not data["shoeboxes"]:
            continue

        min_z = min(box["min"][2] for box in data["shoeboxes"])
        data["elevation"] = min_z

        # Split rooms (real obstacles) from corridors/halls (free area).
        obstacle_boxes = [b for b in data["shoeboxes"] if not is_corridor_space(b["name"])]
        corridor_boxes = [b for b in data["shoeboxes"] if is_corridor_space(b["name"])]

        # --- Door nodes, matched against exact room boundaries ----------
        door_nodes = []
        for box in obstacle_boxes:
            x_min, x_max = box["min"][0], box["max"][0]
            y_min, y_max = box["min"][1], box["max"][1]
            room_has_door = False

            for d_box in data["doors_raw"]:
                if door_adjacent_to_room(d_box, box):
                    room_has_door = True
                    dcx, dcy = d_box["center"][0], d_box["center"][1]
                    snap_pos = (x_min, dcy) if abs(dcx - x_min) < abs(dcx - x_max) else (x_max, dcy)
                    xy_pos = (round(snap_pos[0], 2), round(snap_pos[1], 2))
                    if xy_pos not in data["unique_positions"]:
                        data["unique_positions"].add(xy_pos)
                        door_nodes.append(Node(xy_pos, "door"))

            if not room_has_door:
                # Fallback access point when no door geometry could be
                # matched to this room (e.g. an open-plan boundary).
                synth_pos = (x_min, round((y_min + y_max) / 2, 2))
                xy_pos = (round(synth_pos[0], 2), round(synth_pos[1], 2))
                if xy_pos not in data["unique_positions"]:
                    data["unique_positions"].add(xy_pos)
                    door_nodes.append(Node(xy_pos, "door"))

        # --- Stair nodes, placed at the real stair core's centroid ------
        stair_nodes = []
        for sbox in data["stair_boxes"]:
            pos = (round(sbox["center"][0], 2), round(sbox["center"][1], 2))
            stair_nodes.append(Node(pos, "stair"))
        if stair_nodes:
            raw_stair_map[floor_name] = stair_nodes[0]

        # --- Step 2: walk nodes via free-area decomposition -------------
        if corridor_boxes:
            walk_nodes = walk_nodes_from_corridors(corridor_boxes)
        else:
            floor_bounds = (
                min(b["min"][0] for b in data["shoeboxes"]),
                min(b["min"][1] for b in data["shoeboxes"]),
                max(b["max"][0] for b in data["shoeboxes"]),
                max(b["max"][1] for b in data["shoeboxes"]),
            )
            walk_nodes = walk_nodes_from_free_area(floor_bounds, obstacle_boxes)

        all_floor_nodes = walk_nodes + door_nodes + stair_nodes

        # Restricted zones/obstacles the pathfinding mesh must route
        # around: enclosed rooms and stair cores, using their exact
        # extracted dimensions. Corridors are free area, not obstacles.
        rectangles = [
            (b["min"][0], b["min"][1], b["max"][0], b["max"][1]) for b in obstacle_boxes
        ] + [
            (b["min"][0], b["min"][1], b["max"][0], b["max"][1]) for b in data["stair_boxes"]
        ]

        valid_edges = get_valid_edges(all_floor_nodes, rectangles)
        clean_edges = [e for e in valid_edges if 0.1 < e[2] < 15.0]

        json_output[floor_name] = {
            "elevation": data["elevation"],
            "shoeboxes": data["shoeboxes"],
            "nodes": [{"pos": n.pos, "type": n.node_type} for n in all_floor_nodes],
            "edges": [{"from": e[0].pos, "to": e[1].pos, "distance": e[2]} for e in clean_edges],
        }

    sorted_floors = sorted([f for f in json_output.keys() if f in raw_stair_map], key=lambda f: json_output[f]["elevation"])
    stair_connections = []
    for i in range(len(sorted_floors) - 1):
        f1, f2 = sorted_floors[i], sorted_floors[i + 1]
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