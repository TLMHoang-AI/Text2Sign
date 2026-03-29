#!/usr/bin/env python3
"""
Blender Python script: tự động hoá pipeline
  AMASS .npz  →  SMPL-X Neutral animation  →  Rokoko retarget  →  X-Bot FBX

Yêu cầu:
  - Blender 3.x / 4.x đã cài Rokoko Studio Plugin (Blender addon)
  - File SMPL-X neutral FBX đã setup (hoặc dùng armature tạo từ npz trực tiếp)
  - File X-Bot FBX (T-pose / A-pose)

Cách chạy trong Blender GUI (mở Script editor và paste):
  - Chỉnh AMASS_NPZ_PATH, XBOT_FBX_PATH, OUTPUT_FBX_PATH ở phần CONFIG bên dưới
  - Nhấn Run Script

Cách chạy headless (command line):
  blender --background --python blender_retarget_auto.py -- \\
	--amass amass_output/D0001B_amass.npz \\
	--xbot  standing_x_bot.fbx \\
	--out   xbot_D0001B_animated.fbx

Lưu ý Rokoko Blender Plugin:
  - Plugin cần đăng nhập account Rokoko 1 lần, sau đó offline ok
  - Retargeting nằm trong: N-panel → Rokoko → Retargeting tab
  - Bone list map SMPL-X → Mixamo X-Bot đã được định nghĩa sẵn trong script này
"""

import sys
import os
import argparse
import math
import json

# ── ensure numpy is available in Blender Python ───────────────────────────────
try:
	import numpy as np
except ImportError:
	import subprocess
	subprocess.check_call([sys.executable, "-m", "pip", "install", "numpy"])
	import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG (chỉnh ở đây nếu chạy trong Blender GUI)
# ─────────────────────────────────────────────────────────────────────────────
AMASS_NPZ_PATH = "amass_output/D0001B_amass.npz"
XBOT_FBX_PATH  = "standing_x_bot.fbx"
OUTPUT_FBX_PATH = "xbot_animated.fbx"
FPS            = 30
# ─────────────────────────────────────────────────────────────────────────────


def parse_args_blender():
	"""Parse args sau '--' trong lệnh blender --background --python script.py -- ..."""
	try:
		idx = sys.argv.index("--")
		argv = sys.argv[idx + 1:]
	except ValueError:
		argv = []

	parser = argparse.ArgumentParser()
	parser.add_argument("--amass", default=AMASS_NPZ_PATH)
	parser.add_argument("--xbot",  default=XBOT_FBX_PATH)
	parser.add_argument("--out",   default=OUTPUT_FBX_PATH)
	parser.add_argument("--batch-json", default=None, help="JSON file containing batch items")
	parser.add_argument("--fps",   type=float, default=FPS)
	parser.add_argument("--stabilize", action="store_true", help="Keep model at 0,0,0 (ignore translation)")
	parser.add_argument("--rotate-x", type=float, default=0.0, help="Rotate model around X axis (try 90 for upright)")
	return parser.parse_args(argv)


# ─────────────────────────────────────────────────────────────────────────────
# SMPL-X joint index → Blender bone name (cho armature tự tạo)
# ─────────────────────────────────────────────────────────────────────────────

# AMASS poses vector: [0:3] global_orient, [3:66] body (21j), [66:69] jaw,
#                     [69:72] leye, [72:75] reye,
#                     [75:120] left_hand (15j), [120:165] right_hand (15j)

SMPLX_BODY_JOINTS = [
	"pelvis", "left_hip", "right_hip", "spine1",
	"left_knee", "right_knee", "spine2",
	"left_ankle", "right_ankle", "spine3",
	"left_foot", "right_foot", "neck",
	"left_collar", "right_collar", "head",
	"left_shoulder", "right_shoulder",
	"left_elbow", "right_elbow",
	"left_wrist", "right_wrist",  # joint 21,22 → index in body_pose
]
# body_pose là 21 joints (3:66), không bao gồm pelvis (index 0 = global_orient)

SMPLX_LHAND_JOINTS = [
	"left_index1", "left_index2", "left_index3",
	"left_middle1", "left_middle2", "left_middle3",
	"left_pinky1",  "left_pinky2",  "left_pinky3",
	"left_ring1",   "left_ring2",   "left_ring3",
	"left_thumb1",  "left_thumb2",  "left_thumb3",
]
SMPLX_RHAND_JOINTS = [
	"right_index1", "right_index2", "right_index3",
	"right_middle1", "right_middle2", "right_middle3",
	"right_pinky1",  "right_pinky2",  "right_pinky3",
	"right_ring1",   "right_ring2",   "right_ring3",
	"right_thumb1",  "right_thumb2",  "right_thumb3",
]

# Rokoko Blender plugin bone mapping: source (SMPL-X) → target (Mixamo X-Bot)
# Các tên này phải khớp với tên bone trong armature
ROKOKO_BONE_MAP = {
	# SMPL-X bone name  :  Mixamo X-Bot bone name
	"pelvis"            : "mixamorig:Hips",
	"spine1"            : "mixamorig:Spine",
	"spine2"            : "mixamorig:Spine1",
	"spine3"            : "mixamorig:Spine2",
	"neck"              : "mixamorig:Neck",
	"head"              : "mixamorig:Head",
	"left_collar"       : "LeftCollar",
	"right_collar"      : "RightCollar",
	"left_shoulder"     : "mixamorig:LeftArm",
	"right_shoulder"    : "mixamorig:RightArm",
	"left_elbow"        : "mixamorig:LeftForeArm",
	"right_elbow"       : "mixamorig:RightForeArm",
	"left_wrist"        : "mixamorig:LeftHand",
	"right_wrist"       : "mixamorig:RightHand",
	"left_hip"          : "mixamorig:LeftUpLeg",
	"right_hip"         : "mixamorig:RightUpLeg",
	"left_knee"         : "mixamorig:LeftLeg",
	"right_knee"        : "mixamorig:RightLeg",
	"left_ankle"        : "mixamorig:LeftFoot",
	"right_ankle"       : "mixamorig:RightFoot",
	"left_foot"         : "mixamorig:LeftToeBase",
	"right_foot"        : "mixamorig:RightToeBase",
	# Fingers
	"left_index1"       : "mixamorig:LeftHandIndex1",
	"left_index2"       : "mixamorig:LeftHandIndex2",
	"left_index3"       : "mixamorig:LeftHandIndex3",
	"left_middle1"      : "mixamorig:LeftHandMiddle1",
	"left_middle2"      : "mixamorig:LeftHandMiddle2",
	"left_middle3"      : "mixamorig:LeftHandMiddle3",
	"left_pinky1"       : "mixamorig:LeftHandPinky1",
	"left_pinky2"       : "mixamorig:LeftHandPinky2",
	"left_pinky3"       : "mixamorig:LeftHandPinky3",
	"left_ring1"        : "mixamorig:LeftHandRing1",
	"left_ring2"        : "mixamorig:LeftHandRing2",
	"left_ring3"        : "mixamorig:LeftHandRing3",
	"left_thumb1"       : "mixamorig:LeftHandThumb1",
	"left_thumb2"       : "mixamorig:LeftHandThumb2",
	"left_thumb3"       : "mixamorig:LeftHandThumb3",
	"right_index1"      : "mixamorig:RightHandIndex1",
	"right_index2"      : "mixamorig:RightHandIndex2",
	"right_index3"      : "mixamorig:RightHandIndex3",
	"right_middle1"     : "mixamorig:RightHandMiddle1",
	"right_middle2"     : "mixamorig:RightHandMiddle2",
	"right_middle3"     : "mixamorig:RightHandMiddle3",
	"right_pinky1"      : "mixamorig:RightHandPinky1",
	"right_pinky2"      : "mixamorig:RightHandPinky2",
	"right_pinky3"      : "mixamorig:RightHandPinky3",
	"right_ring1"       : "mixamorig:RightHandRing1",
	"right_ring2"       : "mixamorig:RightHandRing2",
	"right_ring3"       : "mixamorig:RightHandRing3",
	"right_thumb1"      : "mixamorig:RightHandThumb1",
	"right_thumb2"      : "mixamorig:RightHandThumb2",
	"right_thumb3"      : "mixamorig:RightHandThumb3",
}




def find_bone_flexible(arm_obj, bone_name):
	"""Tìm bone trong armature chấp nhận prefix mixamorig: hoặc ko, và case-insensitive."""
	name_lower = bone_name.lower()
	alt_name_lower = ""
	if ":" in name_lower:
		alt_name_lower = name_lower.split(":")[-1]
	else:
		alt_name_lower = "mixamorig:" + name_lower

	# Thử khớp chính xác trước
	if bone_name in arm_obj.pose.bones:
		return arm_obj.pose.bones[bone_name]

	# Duyệt tất cả bones tìm case-insensitive match
	for b in arm_obj.pose.bones:
		b_lower = b.name.lower()
		if b_lower == name_lower or b_lower == alt_name_lower:
			return b
	
	return None


# ─────────────────────────────────────────────────────────────────────────────
# Blender operations
# ─────────────────────────────────────────────────────────────────────────────

def run_in_blender(amass_path: str, xbot_fbx: str, output_fbx: str, fps: float = 30.0):
	"""Chạy toàn bộ pipeline trong Blender."""
	import bpy
	from mathutils import Euler, Matrix, Vector, Quaternion

	print(f"\n{'='*60}")
	print(f"🚀 Blender Retarget Automation")
	print(f"   AMASS  : {amass_path}")
	print(f"   X-Bot  : {xbot_fbx}")
	print(f"   Output : {output_fbx}")
	print(f"{'='*60}\n")

	# ── 1. Reset scene (Sạch hơn nhưng không reset addon) ──────────────────────
	print("Cleaning scene...")
	# Delete all objects
	bpy.ops.object.select_all(action="SELECT")
	bpy.ops.object.delete()
	
	# Remove orphan data
	for block in bpy.data.armatures:
		bpy.data.armatures.remove(block)
	for block in bpy.data.meshes:
		bpy.data.meshes.remove(block)
	for block in bpy.data.actions:
		bpy.data.actions.remove(block)
	for block in bpy.data.materials:
		bpy.data.materials.remove(block)
	
	scene = bpy.context.scene
	scene.render.fps = int(fps)

	# ── 2. Load AMASS .npz ───────────────────────────────────────────────────
	print("Loading AMASS data...")
	data = np.load(amass_path)
	poses     = data["poses"].astype(np.float32)   # (T, 165)
	trans     = data["trans"].astype(np.float32)   # (T, 3)
	T         = poses.shape[0]

	# Decode pose vector → per-joint axis-angle
	global_orient  = poses[:, 0:3]     # (T, 3)
	body_pose      = poses[:, 3:66]    # (T, 63) = 21 joints * 3
	jaw_pose       = poses[:, 66:69]
	lhand_pose     = poses[:, 75:120]  # (T, 45) = 15 joints * 3
	rhand_pose     = poses[:, 120:165]

	scene.frame_start = 1
	scene.frame_end   = T

	# ── 3. Tạo SMPL-X armature thủ công với đầy đủ bones ───────────────────
	print("Tạo SMPL-X armature...")
	bpy.ops.object.armature_add(location=(0, 0, 0))
	smplx_arm_obj = bpy.context.active_object
	smplx_arm_obj.name = "SMPLX_Armature"
	smplx_arm     = smplx_arm_obj.data
	smplx_arm.name = "SMPLX_Armature"

	# Edit mode để tạo bone structure
	bpy.ops.object.mode_set(mode="EDIT")
	edit_bones = smplx_arm.edit_bones

	# Xoá bone mặc định
	for b in list(edit_bones):
		edit_bones.remove(b)

	# Chiều dài bone = 0.1m (chỉ cần đủ để keyframe)
	BONE_LENGTH = 0.1

	def make_bone(name, head, parent_name=None):
		b = edit_bones.new(name)
		b.head = head
		b.tail = (head[0], head[1], head[2] + BONE_LENGTH)
		b.use_connect = False
		if parent_name:
			b.parent = edit_bones[parent_name]
		return b

	# Tạo minimal bone set
	make_bone("pelvis",          (0, 0, 0.9))
	make_bone("spine1",          (0, 0, 1.0), "pelvis")
	make_bone("spine2",          (0, 0, 1.1), "spine1")
	make_bone("spine3",          (0, 0, 1.2), "spine2")
	make_bone("neck",            (0, 0, 1.4), "spine3")
	make_bone("head",            (0, 0, 1.5), "neck")
	make_bone("jaw",             (0, 0.05, 1.5), "head")
	make_bone("left_collar",     (-0.05, 0, 1.35), "spine3")
	make_bone("right_collar",    ( 0.05, 0, 1.35), "spine3")
	make_bone("left_shoulder",   (-0.15, 0, 1.3), "left_collar")
	make_bone("right_shoulder",  ( 0.15, 0, 1.3), "right_collar")
	make_bone("left_elbow",      (-0.35, 0, 1.3), "left_shoulder")
	make_bone("right_elbow",     ( 0.35, 0, 1.3), "right_shoulder")
	make_bone("left_wrist",      (-0.55, 0, 1.3), "left_elbow")
	make_bone("right_wrist",     ( 0.55, 0, 1.3), "right_elbow")
	make_bone("left_hip",        (-0.1, 0, 0.85), "pelvis")
	make_bone("right_hip",       ( 0.1, 0, 0.85), "pelvis")
	make_bone("left_knee",       (-0.1, 0, 0.5),  "left_hip")
	make_bone("right_knee",      ( 0.1, 0, 0.5),  "right_hip")
	make_bone("left_ankle",      (-0.1, 0, 0.1),  "left_knee")
	make_bone("right_ankle",     ( 0.1, 0, 0.1),  "right_knee")
	make_bone("left_foot",       (-0.1, 0.1, 0.0),"left_ankle")
	make_bone("right_foot",      ( 0.1, 0.1, 0.0),"right_ankle")

	# Fingers – left hand
	hand_offset_l = (-0.55, 0, 1.3)
	hand_offset_r = ( 0.55, 0, 1.3)
	for i, jname in enumerate(SMPLX_LHAND_JOINTS):
		row = i % 3
		col = i // 3
		parent_name = "left_wrist" if row == 0 else SMPLX_LHAND_JOINTS[i-1]
		make_bone(jname, (hand_offset_l[0] - col*0.03, 0, hand_offset_l[2] - row*0.02 + 0.02), parent_name)
	for i, jname in enumerate(SMPLX_RHAND_JOINTS):
		row = i % 3
		col = i // 3
		parent_name = "right_wrist" if row == 0 else SMPLX_RHAND_JOINTS[i-1]
		make_bone(jname, (hand_offset_r[0] + col*0.03, 0, hand_offset_r[2] - row*0.02 + 0.02), parent_name)

	bpy.ops.object.mode_set(mode="POSE")
	pose_bones = smplx_arm_obj.pose.bones

	# ── 4. Keyframe AMASS data lên SMPL-X armature ───────────────────────────
	print(f" Keyframing {T} frames...")

	# Xây dựng mapping: joint index → bone name
	all_joints = ["pelvis"] + SMPLX_BODY_JOINTS[1:]  # body: 22 joints (incl pelvis)
	all_joints += ["jaw", "left_eye_smplhf", "right_eye_smplhf"]
	all_joints += SMPLX_LHAND_JOINTS + SMPLX_RHAND_JOINTS

	# poses slice indices tương ứng:
	# global_orient: poses[0:3]
	# body: poses[3:3+21*3] = [3:66]  → 21 joints (hip,knee,... không incl pelvis)
	# jaw: [66:69], leye:[69:72], reye:[72:75]
	# lhand: [75:120], rhand:[120:165]

	# ── 4. Chuẩn bị Pose Data (Bao gồm xoay if rotate_x) ──────────────────────
	def aa_to_matrix(aa_vec):
		"""axis-angle (3,) → mathutils.Matrix 3×3"""
		angle = math.sqrt(aa_vec[0]**2 + aa_vec[1]**2 + aa_vec[2]**2)
		if angle < 1e-8:
			return Matrix.Identity(3)
		axis = Vector((aa_vec[0]/angle, aa_vec[1]/angle, aa_vec[2]/angle))
		return Matrix.Rotation(angle, 3, axis)

	rotate_x_deg = getattr(args, "rotate_x", 0.0)
	rot_mat = Matrix.Rotation(math.radians(rotate_x_deg), 3, 'X') if rotate_x_deg != 0 else None

	bone_aa_map = {}
	if rot_mat:
		print(f"Applying rotation fix in data: {rotate_x_deg} degrees on X")
		bone_aa_map["pelvis"] = [rot_mat @ aa_to_matrix(aa) for aa in global_orient]
	else:
		bone_aa_map["pelvis"] = [aa_to_matrix(aa) for aa in global_orient]

	body_bone_names = SMPLX_BODY_JOINTS[1:]
	for j, bname in enumerate(body_bone_names):
		bone_aa_map[bname] = [aa_to_matrix(aa) for aa in body_pose[:, j*3:(j+1)*3]]
	bone_aa_map["jaw"] = [aa_to_matrix(aa) for aa in jaw_pose]
	for j, bname in enumerate(SMPLX_LHAND_JOINTS):
		bone_aa_map[bname] = [aa_to_matrix(aa) for aa in lhand_pose[:, j*3:(j+1)*3]]
	for j, bname in enumerate(SMPLX_RHAND_JOINTS):
		bone_aa_map[bname] = [aa_to_matrix(aa) for aa in rhand_pose[:, j*3:(j+1)*3]]

	# ── 5. Keyframe AMASS data lên SMPL-X armature ───────────────────────────
	print(f"Keyframing {T} frames...")
	for frame_i in range(T):
		scene.frame_set(frame_i + 1)
		pelvis_bone = pose_bones.get("pelvis")
		if pelvis_bone:
			if getattr(args, "stabilize", False):
				pelvis_bone.location = (0, 0, 0)
			else:
				t = trans[frame_i]
				pelvis_bone.location = (float(t[0]), float(t[1]), float(t[2]))
			pelvis_bone.keyframe_insert("location")

		for bname, mat_frames in bone_aa_map.items():
			pb = pose_bones.get(bname)
			if pb is None:
				continue
			mat = mat_frames[frame_i]            # mathutils.Matrix 3×3
			pb.rotation_mode = 'QUATERNION'
			pb.rotation_quaternion = mat.to_quaternion()
			pb.keyframe_insert("rotation_quaternion")

	bpy.ops.object.mode_set(mode="OBJECT")
	print("✓ SMPL-X animation baked xong!")

	# ── 5. Import X-Bot FBX ──────────────────────────────────────────────────
	print(f"\nImport X-Bot: {xbot_fbx}")
	xbot_abs = os.path.abspath(xbot_fbx)
	if not os.path.exists(xbot_abs):
		print(f"❌ Không tìm thấy file X-Bot: {xbot_abs}")
		return

	bpy.ops.import_scene.fbx(
		filepath=xbot_abs,
		automatic_bone_orientation=True,
		use_anim=False,
	)

	# Tìm X-Bot armature (Strict)
	xbot_arm_obj = None
	for obj in bpy.data.objects:
		if obj.type == "ARMATURE" and obj.name != "SMPLX_Armature":
			xbot_arm_obj = obj
			break

	if xbot_arm_obj is None:
		raise RuntimeError(" Không tìm thấy X-Bot armature (Mixamo X-Bot)!")

	xbot_arm_obj.name = "XBot_Armature"
	print(f"✓ X-Bot armature: {xbot_arm_obj.name}")

	# ── 6. Rokoko Retargeting ─────────────────────────────────────────────────
	print("\nThử dùng Rokoko Studio Live v1.4.3 plugin...")

	import addon_utils
	rokoko_addon_name = "rokoko-studio-live-blender-1-4-3"
	
	if rokoko_addon_name in addon_utils.addons_fake_modules:
		print(f"  🪄 Force enabling addon: {rokoko_addon_name}")
		addon_utils.enable(rokoko_addon_name)
	else:
		print(f"  ⚠ Cảnh báo: Không tìm thấy addon {rokoko_addon_name}")



	# Kiểm tra version plugin và operator rsl (Strict v1.4.3)
	if not hasattr(bpy.ops, "rsl"):
		raise RuntimeError("❌ Rokoko Studio Live (v1.4.3) không khả dụng (thiếu namespace 'rsl')")
	
	rokoko_ops = bpy.ops.rsl
	print("  ✓ Rokoko addon detected (v1.4.3 namespace: rsl)")

	if rokoko_ops:
		try:
			# Deselect all
			bpy.ops.object.select_all(action="DESELECT")

			# Đảm bảo source có action (Rokoko cần action để retarget)
			if not smplx_arm_obj.animation_data or not smplx_arm_obj.animation_data.action:
				print("  ⚠ Cảnh báo: SMPL-X không có action! Đang tạo action dummy...")
				if not smplx_arm_obj.animation_data:
					smplx_arm_obj.animation_data_create()
				# Thêm keyframe dummy nếu cần
				smplx_arm_obj.pose.bones[0].keyframe_insert(data_path="location", frame=1)

			# Rokoko v1.4.3 sử dụng scene properties để track source/target
			print(f"  Đang thiết lập Source: {smplx_arm_obj.name}, Target: {xbot_arm_obj.name}")
			try:
				scene.rsl_retargeting_armature_source = smplx_arm_obj
				scene.rsl_retargeting_armature_target = xbot_arm_obj
			except Exception as e:
				print(f"   Cảnh báo: Không thể gán trực tiếp source/target properties: {e}")

			# --- MANUAL BONE LIST POPULATION ---
			print("  Đang tự động điền danh sách bone cho Rokoko...")
			try:
				scene.rsl_retargeting_bone_list.clear()
			except:
				pass
			
			added_count = 0
			for src_bone_name, tgt_bone_hint in ROKOKO_BONE_MAP.items():
				pb_target = find_bone_flexible(xbot_arm_obj, tgt_bone_hint)
				if pb_target:
					try:
						item = scene.rsl_retargeting_bone_list.add()
						item.bone_name_source = src_bone_name
						item.bone_name_target = pb_target.name
						added_count += 1
					except Exception as e:
						print(f" Lỗi khi add bone item ({src_bone_name}): {e}")
			
			print(f" Đã thêm {added_count} bones vào danh sách retargeting.")

			# Force update scene
			bpy.context.view_layer.update()

			# Execute Retarget Animation
			if hasattr(bpy.ops.rsl, "retarget_animation"):
				print("  Rokoko: Execution Retarget Animation...")
				# Gọi trực tiếp - Trong background mode, Rokoko v1.4.3 tự lấy context từ scene properties
				bpy.ops.rsl.retarget_animation('EXEC_DEFAULT')
				print("  ✓ Rokoko retarget animation executed successfully!")
			else:
				raise RuntimeError(" Không tìm thấy operator 'bpy.ops.rsl.retarget_animation'")

		except Exception as e:
			print(f" Lỗi trong quá trình Rokoko retarget: {e}")
			raise e
	else:
		msg = "Rokoko Studio Live addon không tìm thấy! Script yêu cầu Rokoko để retarget."
		print(msg)
		raise RuntimeError(msg)

	# ── 7. Export X-Bot animated FBX ─────────────────────────────────────────
	print(f"\nExport FBX: {output_fbx}")
	out_abs = os.path.abspath(output_fbx)

	bpy.ops.object.select_all(action="DESELECT")
	xbot_arm_obj.select_set(True)
	# Chọn cả mesh children của X-Bot
	for obj in bpy.data.objects:
		if obj.parent == xbot_arm_obj:
			obj.select_set(True)

	bpy.context.view_layer.objects.active = xbot_arm_obj

	# Debug bone position
	scene.frame_set(1)
	hips = xbot_arm_obj.pose.bones.get("mixamorig:Hips")
	if hips:
		print(f"Debug: X-Bot Hips position at frame 1: {hips.head}")
		if hips.head.length > 5000:
			 print("CẢNH BÁO: Nhân vật bị văng ra quá xa! Kiểm tra lại rotation/translation data.")

	bpy.ops.export_scene.fbx(
		filepath=out_abs,
		use_selection=True,
		bake_anim=True,
		bake_anim_use_all_actions=True,
		bake_anim_step=1.0,
		bake_anim_simplify_factor=0.0,
		add_leaf_bones=False,
		path_mode="COPY",
		embed_textures=False,
		axis_forward="-Z",
		axis_up="Y",
		apply_scale_options='FBX_SCALE_ALL' # Thêm để ổn định unit
	)
	print(f"✓ Đã export: {out_abs}")
	print(f"\n{'='*60}")
	print(f"Pipeline DONEDONE!")
	print(f"   Output: {out_abs}")
	print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
	# Khi chạy trong Blender, bpy luôn available
	try:
		import bpy  # noqa: F401
		_in_blender = True
	except ImportError:
		_in_blender = False

if _in_blender:
    args = parse_args_blender()
    if args.batch_json:
        with open(args.batch_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
        items = payload.get("items", [])
        default_xbot = payload.get("xbot") or args.xbot
        default_fps = payload.get("fps") or args.fps
        for idx, item in enumerate(items, start=1):
            amass_path = item.get("amass") or args.amass
            output_fbx = item.get("out") or args.out
            xbot_fbx = item.get("xbot") or default_xbot
            fps = item.get("fps") or default_fps
            print(f"\n[Batch {idx}/{len(items)}]")
            run_in_blender(
                amass_path=amass_path,
                xbot_fbx=xbot_fbx,
                output_fbx=output_fbx,
                fps=fps,
            )
    else:
        run_in_blender(
            amass_path=args.amass,
            xbot_fbx=args.xbot,
            output_fbx=args.out,
            fps=args.fps,
        )
else:
    print("❌ Script này phải chạy bên trong Blender!")
    print("   Dùng: blender --background --python blender_retarget_auto.py -- --amass X --xbot Y --out Z")
    sys.exit(1)

