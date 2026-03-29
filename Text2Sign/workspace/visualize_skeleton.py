import cv2
import json
import os
import numpy as np
import mediapipe as mp

def visualize_motion(video_path, json_path, output_path):
    print(f"Visualizing motion from {json_path} on {video_path}")
    
    # Load motion data
    with open(json_path, 'r') as f:
        motion_data = json.load(f)
    print(f"Loaded {len(motion_data)} frames of motion data")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return

    # Video properties
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    # Output writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    
    # Simplified connections for Hands
    HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4), # Thumb
        (0, 5), (5, 6), (6, 7), (7, 8), # Index
        (0, 9), (9, 10), (10, 11), (11, 12), # Middle
        (0, 13), (13, 14), (14, 15), (15, 16), # Ring
        (0, 17), (17, 18), (18, 19), (19, 20)  # Pinky
    ]
    
    # Pose connections (simplified)
    POSE_CONNECTIONS = [
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), # Arms
        (11, 23), (12, 24), (23, 24), # Torso
        (23, 25), (24, 26), (25, 27), (26, 28), # Legs
        (27, 29), (28, 30), (29, 31), (30, 32), # Feet
        (15, 17), (15, 19), (15, 21), (17, 19), # Left Hand Palm/Wrists approximation
        (16, 18), (16, 20), (16, 22), (18, 20), # Right Hand Palm/Wrists approximation
    ]

    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_idx < len(motion_data):
            frame_info = motion_data[frame_idx]
            
            # --- Draw Pose ---
            pose_landmarks = frame_info.get("pose")
            if pose_landmarks:
                for i, lm in enumerate(pose_landmarks):
                    if lm and lm.get('visibility', 0) > 0.5:
                        cx, cy = int(lm['x'] * width), int(lm['y'] * height)
                        cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)
                
                for i, j in POSE_CONNECTIONS:
                    if i < len(pose_landmarks) and j < len(pose_landmarks):
                        lm_i = pose_landmarks[i]
                        lm_j = pose_landmarks[j]
                        if (lm_i and lm_j and lm_i.get('visibility', 0) > 0.5 and lm_j.get('visibility', 0) > 0.5):
                            x1, y1 = int(lm_i['x'] * width), int(lm_i['y'] * height)
                            x2, y2 = int(lm_j['x'] * width), int(lm_j['y'] * height)
                            cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # --- Draw Left Hand ---
            lh_landmarks = frame_info.get("left_hand")
            if lh_landmarks:
                for lm in lh_landmarks:
                    if lm:
                        cx, cy = int(lm['x'] * width), int(lm['y'] * height)
                        cv2.circle(frame, (cx, cy), 2, (255, 0, 0), -1) # Blue for hands
                for i, j in HAND_CONNECTIONS:
                    if i < len(lh_landmarks) and j < len(lh_landmarks):
                        lm_i, lm_j = lh_landmarks[i], lh_landmarks[j]
                        if lm_i and lm_j:
                            x1, y1 = int(lm_i['x'] * width), int(lm_i['y'] * height)
                            x2, y2 = int(lm_j['x'] * width), int(lm_j['y'] * height)
                            cv2.line(frame, (x1, y1), (x2, y2), (255, 0, 0), 1)

            # --- Draw Right Hand ---
            rh_landmarks = frame_info.get("right_hand")
            if rh_landmarks:
                for lm in rh_landmarks:
                    if lm:
                        cx, cy = int(lm['x'] * width), int(lm['y'] * height)
                        cv2.circle(frame, (cx, cy), 2, (0, 0, 255), -1) # Red for hands
                for i, j in HAND_CONNECTIONS:
                    if i < len(rh_landmarks) and j < len(rh_landmarks):
                        lm_i, lm_j = rh_landmarks[i], rh_landmarks[j]
                        if lm_i and lm_j:
                            x1, y1 = int(lm_i['x'] * width), int(lm_i['y'] * height)
                            x2, y2 = int(lm_j['x'] * width), int(lm_j['y'] * height)
                            cv2.line(frame, (x1, y1), (x2, y2), (0, 0, 255), 1)

            # --- Draw Face (Simplified - contours/tesselation is too dense, drawing points only) ---
            face_landmarks = frame_info.get("face")
            if face_landmarks:
                # Face mesh has 468 points, drawing all lines is messy. Draw points.
                # Or draw specifics: lips (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95)
                # Drawing every 10th point for performance and reduced clutter
                for i, lm in enumerate(face_landmarks):
                    if lm: # No visibility check for face usually needed in holistic
                        cx, cy = int(lm['x'] * width), int(lm['y'] * height)
                        cv2.circle(frame, (cx, cy), 1, (255, 255, 255), -1) # White for face

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    print(f"Visualization saved to {output_path}")

if __name__ == "__main__":
    video_file = r"e:\Text2Sign\dic\D0001B.webm"
    json_file = r"e:\Text2Sign\workspace\motion_data.json"
    output_file = r"e:\Text2Sign\workspace\skeleton_viz.mp4"
    
    if os.path.exists(video_file) and os.path.exists(json_file):
        visualize_motion(video_file, json_file, output_file)
    else:
        print("Error: Input files not found.")
