import sys
import ifcopenshell
import ifcopenshell.util.placement

def get_element_position(element):
    try:
        matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
        return (round(float(matrix[0][3]), 2), round(float(matrix[1][3]), 2), round(float(matrix[2][3]), 2))
    except Exception:
        return None

def inspect_ifc(ifc_path):
    model = ifcopenshell.open(ifc_path)
    print(f"=== Inspecting IFC: {ifc_path} ===")
    
    storeys = model.by_type("IfcBuildingStorey")
    print(f"\n[Storeys] Count: {len(storeys)}")
    for s in storeys:
        print(f"  - Storey: {s.Name}, Elevation: {getattr(s, 'Elevation', 'N/A')}")

    spaces = model.by_type("IfcSpace")
    print(f"\n[Spaces / Rooms] Count: {len(spaces)}")
    for sp in spaces:
        name = sp.Name or sp.LongName or f"Space_{sp.id()}"
        pos = get_element_position(sp)
        print(f"  - Space: {name} | Position: {pos}")

    doors = model.by_type("IfcDoor")
    print(f"\n[Doors] Count: {len(doors)}")
    for d in doors[:10]:
        name = d.Name or f"Door_{d.id()}"
        pos = get_element_position(d)
        print(f"  - Door: {name} | Position: {pos}")
    if len(doors) > 10:
        print(f"  ... and {len(doors) - 10} more doors.")

    stairs = model.by_type("IfcStair")
    print(f"\n[Stairs] Count: {len(stairs)}")
    for st in stairs:
        name = st.Name or f"Stair_{st.id()}"
        pos = get_element_position(st)
        print(f"  - Stair: {name} | Position: {pos}")

if __name__ == "__main__":
    file_to_inspect = sys.argv[1] if len(sys.argv) > 1 else "sample_building.ifc"
    inspect_ifc(file_to_inspect)