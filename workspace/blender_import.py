import bpy
import json
import os
import math
import mathutils

# Configuration
JSON_PATH = r"e:\Text2Sign\workspace\motion_data.json"
SCALE_FACTOR = 3.0
FRAME_RATE = 30

def to_blender(lm):
    return mathutils.Vector((
        (lm['x'] - 0.5) * SCALE_FACTOR,
        -lm['z'] * SCALE_FACTOR,
        -(lm['y'] - 0.5) * SCALE_FACTOR
    ))

def import_and_viz():
    if not os.path.exists(JSON_PATH):
        print(f"Error: JSON file not found.")
        return

    # Cleanup
    for cname in ["Sign_Visuals", "SignLanguage_Rig"]:
        if cname in bpy.data.collections:
            col = bpy.data.collections[cname]
            for obj in col.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(col)
        
    col = bpy.data.collections.new("Sign_Visuals")
    bpy.context.scene.collection.children.link(col)

    with open(JSON_PATH, 'r') as f:
        motion_data = json.load(f)

    landmark_empties = {}
    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = len(motion_data)
    
    print("Creating Empties...")
    for i, frame_data in enumerate(motion_data):
        bpy.context.scene.frame_set(i)
        
        def set_empty(name, loc):
            if name not in landmark_empties:
                bpy.ops.object.empty_add(type='PLAIN_AXES', radius=0.01 * SCALE_FACTOR, location=loc)
                obj = bpy.context.active_object
                obj.name = name
                for c in obj.users_collection: c.objects.unlink(obj)
                col.objects.link(obj)
                landmark_empties[name] = obj
            
            obj = landmark_empties[name]
            obj.location = loc
            obj.keyframe_insert(data_path="location")

        pose = frame_data.get("pose")
        pose_world = {} # Idx -> Vector
        if pose:
            for idx, lm in enumerate(pose):
                loc = to_blender(lm)
                set_empty(f"pose_{idx}", loc)
                pose_world[idx] = loc

        # Enhanced Hand Processing with Rotation Alignment
        def process_hand(hand_data, prefix, pose_wrist_idx, pose_elbow_idx):
            if not hand_data or pose_wrist_idx not in pose_world: return
            
            # 1. Get Global Anchor (Wrist)
            pose_wrist = pose_world[pose_wrist_idx]
            
            # 2. Scale
            # 0.15m (Hand Size) / 3.0 (Scale) = 0.05
            GLOBAL_HAND_SCALE = 0.05 
            
            # 3. Rotation Alignment
            # We want the hand's "Forward" Vector to align with the Arm's "Forward" Vector.
            rotation_quat = mathutils.Quaternion((1, 0, 0, 0)) # Identity default
            
            if pose_elbow_idx in pose_world and len(hand_data) > 9:
                pose_elbow = pose_world[pose_elbow_idx]
                
                # Arm Vector (Elbow -> Wrist)
                vec_arm = (pose_wrist - pose_elbow).normalized()
                
                # Hand Vector (Wrist 0 -> Middle MCP 9)
                # Local space
                hw_local = mathutils.Vector((hand_data[0]['x'], -hand_data[0]['z'], -hand_data[0]['y']))
                hm_local = mathutils.Vector((hand_data[9]['x'], -hand_data[9]['z'], -hand_data[9]['y']))
                vec_hand = (hm_local - hw_local).normalized()
                
                # Calculate Rotation to align vec_hand to vec_arm
                # rotation_difference gives quaternion transfoming A to B
                rotation_quat = vec_hand.rotation_difference(vec_arm)

            # 4. Process Points
            # Hand Wrist Local Reference
            wrist_local_ref = mathutils.Vector((hand_data[0]['x'], -hand_data[0]['z'], -hand_data[0]['y']))
            
            for idx, lm in enumerate(hand_data):
                v_local = mathutils.Vector((lm['x'], -lm['z'], -lm['y']))
                
                # Center around wrist
                delta = v_local - wrist_local_ref
                
                # Apply Rotation
                delta.rotate(rotation_quat)
                
                # Apply Scale
                delta *= (SCALE_FACTOR * GLOBAL_HAND_SCALE) # Correction: Apply Scale factor
                # Actually, GLOBAL_HAND_SCALE is a modifier on top of SCALE_FACTOR?
                # No, SCALE_FACTOR converts unitless -> Blender Units.
                # Hand coords are unitless (0-1).
                # (0-1) * SCALE_FACTOR (3.0) = 3 meters. Too big.
                # So we multiply by 0.05 (Scale down 20x).
                
                global_pos = pose_wrist + delta
                
                set_empty(f"{prefix}_{idx}", global_pos)

        # Left Hand: Wrist 15, Elbow 13
        process_hand(frame_data.get("left_hand"), "left_hand", 15, 13)
        # Right Hand: Wrist 16, Elbow 14
        process_hand(frame_data.get("right_hand"), "right_hand", 16, 14)

    # 2. PROTOTYPE STICK
    bpy.context.scene.frame_set(0)
    
    bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=1, location=(0,0,0))
    master_stick = bpy.context.active_object
    master_stick.name = "Master_Stick"
    
    # Edit Mode Transform: Rotate to Y+ and Base Pivot
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.rotate(value=math.pi/2, orient_axis='X') # Along Y
    bpy.ops.transform.translate(value=(0, 0.5, 0)) # Base at Origin
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Create Materials
    mat_green = bpy.data.materials.new("Mat_Green")
    mat_green.diffuse_color = (0, 1, 0, 1)
    
    mat_blue = bpy.data.materials.new("Mat_Blue")
    mat_blue.diffuse_color = (0, 0, 1, 1)
    
    mat_red = bpy.data.materials.new("Mat_Red")
    mat_red.diffuse_color = (1, 0, 0, 1)

    master_stick.hide_render = True
    master_stick.hide_viewport = True

    # 3. Create Instances
    POSE_CONNECTIONS = [
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
        (11, 23), (12, 24), (23, 24),
        (23, 25), (24, 26), (25, 27), (26, 28),
        (27, 29), (28, 30), (29, 31), (30, 32)
    ]
    HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (0, 9), (9, 10), (10, 11), (11, 12),
        (0, 13), (13, 14), (14, 15), (15, 16),
        (0, 17), (17, 18), (18, 19), (19, 20)
    ]
    BRIDGES = [("pose_15", "left_hand_0"), ("pose_16", "right_hand_0")]

    def make_stick(s_name, e_name, mat, thickness):
        if s_name not in landmark_empties or e_name not in landmark_empties: return
        
        new_ob = master_stick.copy()
        new_ob.data = master_stick.data.copy()
        new_ob.name = f"Stick_{s_name}_{e_name}"
        new_ob.hide_render = False
        new_ob.hide_viewport = False
        col.objects.link(new_ob)
        
        new_ob.data.materials.append(mat)
        
        # Scale Y by 1.1 for smoothing
        new_ob.scale = (thickness, 1.1, thickness) 
        
        c1 = new_ob.constraints.new('COPY_LOCATION')
        c1.target = landmark_empties[s_name]
        
        c2 = new_ob.constraints.new('STRETCH_TO')
        c2.target = landmark_empties[e_name]
        c2.volume = 'NO_VOLUME'
    
    rad_body = 0.04 * SCALE_FACTOR
    rad_hand = 0.015 * SCALE_FACTOR
    
    print("Building Body...")
    for s, e in POSE_CONNECTIONS:
        make_stick(f"pose_{s}", f"pose_{e}", mat_green, rad_body)
        
    for s, e in HAND_CONNECTIONS:
        make_stick(f"left_hand_{s}", f"left_hand_{e}", mat_blue, rad_hand)
        make_stick(f"right_hand_{s}", f"right_hand_{e}", mat_red, rad_hand)
        
    for s_name, e_name in BRIDGES:
        make_stick(s_name, e_name, mat_green, rad_hand)

    print("Done! Press Play.")

if __name__ == "__main__":
    import_and_viz()
