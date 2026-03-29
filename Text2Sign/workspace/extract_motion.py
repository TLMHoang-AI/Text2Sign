import cv2
import mediapipe as mp
import json
import os
import sys

def extract_landmarks(video_path, output_path):
    print(f"Processing video: {video_path}")
    
    mp_holistic = mp.solutions.holistic
    
    # Initialize Holistic model
    # min_detection_confidence and min_tracking_confidence can be adjusted
    with mp_holistic.Holistic(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        static_image_mode=False,
        model_complexity=1) as holistic:
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file {video_path}")
            return

        frame_data = []
        frame_idx = 0

        while cap.isOpened():
            success, image = cap.read()
            if not success:
               # print("Ignoring empty camera frame.")
                break

            # To improve performance, optionally mark the image as not writeable to
            # pass by reference.
            image.flags.writeable = False
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            results = holistic.process(image)

            # Landmarks extraction
            frame_landmarks = {
                "frame": frame_idx,
                "pose": None,
                "left_hand": None,
                "right_hand": None,
                "face": None # Start with face as well, though might not need all
            }
            
            # Helper to convert landmark list to dict list
            def landmarks_to_list(landmarks):
                if not landmarks:
                    return None
                return [{"x": lm.x, "y": lm.y, "z": lm.z, "visibility": getattr(lm, 'visibility', 0.0)} for lm in landmarks.landmark]

            frame_landmarks["pose"] = landmarks_to_list(results.pose_landmarks)
            frame_landmarks["left_hand"] = landmarks_to_list(results.left_hand_landmarks)
            frame_landmarks["right_hand"] = landmarks_to_list(results.right_hand_landmarks)
            frame_landmarks["face"] = landmarks_to_list(results.face_landmarks) 

            frame_data.append(frame_landmarks)
            frame_idx += 1

        cap.release()
        
        # Save to JSON
        try:
            with open(output_path, 'w') as f:
                json.dump(frame_data, f, indent=None) # Compact JSON to save space, or indent=2 for readability
            print(f"Successfully saved motion data to {output_path}")
            print(f"Total frames processed: {len(frame_data)}")
        except Exception as e:
            print(f"Error saving JSON: {e}")

if __name__ == "__main__":
    # Hardcoded for the sample as per plan, but can be argued
    video_file = r"e:\Text2Sign\dic\D0001B.webm"
    output_file = r"e:\Text2Sign\workspace\motion_data.json"
    
    if not os.path.exists(video_file):
        print(f"Error: Video file not found: {video_file}")
    else:
        extract_landmarks(video_file, output_file)
