import math

class Node:
    def __init__(self, pos, node_type="walk"):
        self.pos = pos  # (x, y)
        self.node_type = node_type  # "walk", "door", "stair"

def ccw(A, B, C):
    return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

def intersect(A, B, C, D):
    return ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D)

def intersects_interior(p1, p2, rect):
    rx1, ry1, rx2, ry2 = rect
    xmin, xmax = min(rx1, rx2), max(rx1, rx2)
    ymin, ymax = min(ry1, ry2), max(ry1, ry2)
    
    mid_x = (p1[0] + p2[0]) / 2.0
    mid_y = (p1[1] + p2[1]) / 2.0
    if xmin < mid_x < xmax and ymin < mid_y < ymax:
        return True
    
    rect_edges = [
        ((xmin, ymin), (xmax, ymin)),
        ((xmax, ymin), (xmax, ymax)),
        ((xmax, ymax), (xmin, ymax)),
        ((xmin, ymax), (xmin, ymin))
    ]
    
    for seg1, seg2 in rect_edges:
        if intersect(p1, p2, seg1, seg2):
            return True
    return False

def get_valid_edges(nodes, rectangles):
    edges = []
    n = len(nodes)
    for i in range(n):
        for j in range(i + 1, n):
            p1, p2 = nodes[i].pos, nodes[j].pos
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            
            blocked = False
            for rect in rectangles:
                if intersects_interior(p1, p2, rect):
                    blocked = True
                    break
            if not blocked:
                edges.append((nodes[i], nodes[j], round(dist, 2)))
    return edges