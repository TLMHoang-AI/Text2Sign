import bpy
import os
import sys

# Output file for bone info
OUTPUT_FILE = r"e:\Text2Sign\workspace\model_info.txt"
FBX_PATH = r"e:\Text2Sign\workspace\muschelman.fbx"

def inspect_model():
    # Clear scene
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    # Import FBX
    if not os.path.exists(FBX_PATH):
        print(f"Error: File not found {FBX_PATH}")
        return

    print(f"Importing {FBX_PATH}...")
    bpy.ops.import_scene.fbx(filepath=FBX_PATH)
    
    info = []
    
    info.append("All Objects in File:")
    armature = None
    for obj in bpy.data.objects:
        info.append(f"  Name: {obj.name}, Type: {obj.type}, Parent: {obj.parent.name if obj.parent else 'None'}")
        if obj.type == 'ARMATURE':
            armature = obj

    if armature:
        info.append(f"Armature Found: {armature.name}")
        info.append("Bones List:")
        for bone in armature.data.bones:
            info.append(f"  {bone.name}")
            
        # Also print hierarchy structure for key bones
        info.append("\nBone Hierarchy (Parent -> Child):")
        for bone in armature.data.bones:
            if bone.parent is None:
                print_hierarchy(bone, 0, info)
                
    else:
        info.append("No Armature found in the FBX.")
        
    # Write to file
    with open(OUTPUT_FILE, 'w') as f:
        f.write("\n".join(info))
        
    print(f"Info saved to {OUTPUT_FILE}")

def print_hierarchy(bone, level, info_list):
    indent = "  " * level
    info_list.append(f"{indent}- {bone.name}")
    for child in bone.children:
        print_hierarchy(child, level + 1, info_list)

if __name__ == "__main__":
    inspect_model()
