import numpy as np
from node_sol_v1 import Node

def generate_grid_walk_nodes(shoeboxes, n=1.0):
    if not shoeboxes:
        return []

    # 1. Calculate the Minimum Bounding Rectangle (MBR) of all rooms + 1 unit extra
    min_x = min(box["min"][0] for box in shoeboxes) - 1.0
    min_y = min(box["min"][1] for box in shoeboxes) - 1.0
    max_x = max(box["max"][0] for box in shoeboxes) + 1.0
    max_y = max(box["max"][1] for box in shoeboxes) + 1.0
    
    g_x, g_y = min_x, min_y
    g_w = max_x - min_x
    g_h = max_y - min_y

    # 2. Map shoeboxes to restricted zones (x, y, width, height)
    restricted_zones = [
        (box["min"][0], box["min"][1], 
         box["max"][0] - box["min"][0], 
         box["max"][1] - box["min"][1])
        for box in shoeboxes
    ]

    walk_nodes = []
    
    # 3. Generate the nxn grid and extract free-space centroids
    for i in range(int(np.ceil(g_w / n))):
        for j in range(int(np.ceil(g_h / n))):
            sq_x = g_x + (i * n)
            sq_y = g_y + (j * n)

            # Keep square strictly inside the padded MBR
            if sq_x + n > g_x + g_w or sq_y + n > g_y + g_h:
                continue

            # Check if square intersects with any room (restricted zone)
            intersects_restricted = False
            for z_x, z_y, z_w, z_h in restricted_zones:
                if (sq_x + n > z_x and sq_x < z_x + z_w and
                    sq_y + n > z_y and sq_y < z_y + z_h):
                    intersects_restricted = True
                    break
            
            # If open space, create a walk node at the centroid
            if not intersects_restricted:
                c_x = round(sq_x + n / 2.0, 2)
                c_y = round(sq_y + n / 2.0, 2)
                walk_nodes.append(Node((c_x, c_y), "walk"))
                
    return walk_nodes