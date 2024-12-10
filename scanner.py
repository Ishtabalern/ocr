import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageEnhance
import time
import os

def select_folder():
    """Open a dialog to select the folder containing images."""
    global image_files, image_index
    folder_path = filedialog.askdirectory()
    if not folder_path:
        return

    # List all image files in the selected folder
    image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff'))]
    if not image_files:
        scanned_text.set("No image files found in the selected folder!")
        return

    image_index = 0
    load_image(image_files[image_index])

def load_image(image_path):
    """Load an image and display it on the canvas."""
    global original_image, image_width, image_height, image_on_canvas

    original_image = Image.open(image_path)
    image_width, image_height = original_image.size

    canvas.config(scrollregion=(0, 0, image_width, image_height))  # Update scrollable region
    canvas.delete("all")
    photo = ImageTk.PhotoImage(original_image)
    image_on_canvas = canvas.create_image(0, 0, anchor=tk.NW, image=photo)
    canvas.image = photo

    scanned_text.set(f"Loaded: {os.path.basename(image_path)}")

def start_batch_scanning():
    """Start scanning all images in the folder."""
    if not image_files:
        scanned_text.set("No images loaded!")
        return

    for idx, image_path in enumerate(image_files):
        scanned_text.set(f"Scanning {idx + 1}/{len(image_files)}: {os.path.basename(image_path)}")
        root.update()

        # Load the current image
        load_image(image_path)

        # Apply the scanning effect
        for y in range(0, image_height, 10):
            canvas.delete("scanner")
            canvas.create_line(0, y, image_width, y, fill="red", width=2, tags="scanner")
            canvas.update()
            time.sleep(0.02)

        # Process the image
        process_and_save(image_path)

    scanned_text.set("Batch scanning complete!")

def process_and_save(image_path):
    """Apply the scanning effect and save the processed image."""
    enhancer = ImageEnhance.Brightness(original_image)
    bright_image = enhancer.enhance(1.5)  # Increase brightness

    enhancer = ImageEnhance.Contrast(bright_image)
    scanned_image = enhancer.enhance(1.8)  # Increase contrast

    # Save the processed image in the same folder with a new name
    folder, filename = os.path.split(image_path)
    name, ext = os.path.splitext(filename)
    save_path = os.path.join(folder, f"{name}_scanned{ext}")
    scanned_image.save(save_path)

# Initialize the main window
root = tk.Tk()
root.title("Batch Mimic Scanner")

# Create a frame for the canvas and scrollbar
canvas_frame = tk.Frame(root)
canvas_frame.pack(fill=tk.BOTH, expand=True)

# Create a scrollable canvas
canvas = tk.Canvas(canvas_frame, bg="white")
canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

scrollbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
canvas.configure(yscrollcommand=scrollbar.set)

# Create a frame for control buttons and status
control_frame = tk.Frame(root)
control_frame.pack(fill=tk.X)

# Create buttons
load_button = tk.Button(control_frame, text="Select Folder", command=select_folder, font=("Arial", 14))
load_button.pack(side=tk.LEFT, padx=5, pady=5)

scan_button = tk.Button(control_frame, text="Start Batch Scan", command=start_batch_scanning, font=("Arial", 14))
scan_button.pack(side=tk.LEFT, padx=5, pady=5)

# Create a label to display the status
scanned_text = tk.StringVar()
scanned_text.set("Ready to scan...")
status_label = tk.Label(control_frame, textvariable=scanned_text, font=("Arial", 12))
status_label.pack(side=tk.LEFT, padx=5)

# Variables for batch scanning
image_files = []  # List of image file paths
image_index = 0   # Current image index in the batch

# Run the application
root.mainloop()

#C:/Users/CEO Ivo John Barroba/Downloads/sample.jpg