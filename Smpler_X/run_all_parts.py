import os
import subprocess
import glob

# Configuration
PRETRAINED_MODEL = "smpler_x_h32"  # Options: smpler_x_s32, smpler_x_b32, smpler_x_l32, smpler_x_h32
FPS = 30
OUTPUT_BASE = "output_smplerx"

# List specific part numbers to run (e.g., [1, 5, 10]). 
# If empty [], it will run all 'input_part_*' folders found.
PARTS_TO_RUN = [25, 26] 

def run_inference():
    # Get all input_part folders
    if PARTS_TO_RUN:
        input_folders = [f"input_part_{p}" for p in PARTS_TO_RUN if os.path.exists(f"input_part_{p}")]
        # Sort them numerically if they are like input_part_1, input_part_2...
        input_folders.sort(key=lambda x: int(x.split('_')[-1]))
    else:
        input_folders = sorted(glob.glob("input_part_*"), key=lambda x: int(x.split('_')[-1]) if x.split('_')[-1].isdigit() else x)
    
    if not input_folders:
        print(f"No matching folders found for parts: {PARTS_TO_RUN}" if PARTS_TO_RUN else "No 'input_part_*' folders found.")
        return

    # Ensure the output base directory exists
    if not os.path.exists(OUTPUT_BASE):
        os.makedirs(OUTPUT_BASE)

    cwd = os.getcwd()

    for folder in input_folders:
        videos_folder = os.path.join(cwd, folder)
        output_dir = os.path.join(cwd, OUTPUT_BASE, folder)

        print("-" * 56)
        print(f"Processing folder: {folder}")
        print(f"Input: {videos_folder}")
        print(f"Output: {output_dir}")
        print("-" * 56)

        # Ensure output folder for this part exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Environment variables for Docker Compose
        env = os.environ.copy()
        env["VIDEOS_FOLDER"] = videos_folder
        env["OUTPUT_DIR"] = output_dir
        env["PRETRAINED_MODEL"] = PRETRAINED_MODEL

        # Run Docker Compose command
        command = [
            "docker", "compose", "run", "--rm", "smplerx",
            "--videos_folder", "/videos",
            "--demo_results_root", "/output",
            "--fps", str(FPS)
        ]

        try:
            subprocess.run(command, env=env, check=True)
            print(f"Finished processing {folder}\n")
        except subprocess.CalledProcessError as e:
            print(f"Error processing {folder}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")

    print("All parts completed!")

if __name__ == "__main__":
    run_inference()
