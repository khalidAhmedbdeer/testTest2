from flask import Flask, render_template, request, jsonify, send_file
from PIL import Image
import os
from io import BytesIO
import uuid
import zipfile
import hashlib
import json

app = Flask(__name__)

# Set upload folder path
UPLOAD_FOLDER = 'uploads/'
# Set watermark folder path
WATERMARK_FOLDER = 'watermark/'
WATERMARK_FILENAME = 'watermark.png'
WATERMARK_PATH = os.path.join(WATERMARK_FOLDER, WATERMARK_FILENAME)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload and watermark folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(WATERMARK_FOLDER):
    os.makedirs(WATERMARK_FOLDER)

# Load processed files mapping from JSON file
processed_files_path = os.path.join(UPLOAD_FOLDER, 'processed_files.json')
if os.path.exists(processed_files_path):
    with open(processed_files_path, 'r') as f:
        processed_files = json.load(f)
else:
    processed_files = {}

# Store the filenames of resized images globally for creating the ZIP
resized_filenames = []

@app.route('/')

def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global resized_filenames
    resized_filenames.clear()  # Clear the list when new files are uploaded

    if 'images' not in request.files:
        return jsonify({"error": "No file part"}), 400

    files = request.files.getlist('images')
    resized_images = []

    # Check if the watermark image exists
    if not os.path.exists(WATERMARK_PATH):
        return jsonify({"error": "Watermark file not found"}), 500

    # Load the watermark image
    watermark = Image.open(WATERMARK_PATH).convert("RGBA")

    for file in files:
        if file.filename == '':
            continue

        # Check if the file is either JPEG or JPG
        if file and (file.filename.lower().endswith('.jpeg') or file.filename.lower().endswith('.jpg')):
            # Read file content
            file_content = file.read()

            # Compute MD5 hash of the file content
            file_hash = hashlib.md5(file_content).hexdigest()

            # Check if the file has already been processed
            if file_hash in processed_files:
                # File already processed, use existing output
                filename = processed_files[file_hash]
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(output_path):
                    resized_images.append({
                        "filename": filename,
                        "url": f'/uploads/{filename}'
                    })
                    # Add the filename to the global list for ZIP download
                    resized_filenames.append(output_path)
                    continue  # Skip processing
                else:
                    # Output file does not exist, remove from mapping
                    del processed_files[file_hash]

            # Proceed to process the file
            # Recreate file stream from content
            img = Image.open(BytesIO(file_content)).convert("RGBA")  # Ensure the uploaded image has an alpha channel

            # Define the maximum dimensions (1920x1080)
            max_width = 1920
            max_height = 1080

            # Get the original dimensions
            width, height = img.size

            # Calculate the scaling factor to maintain aspect ratio
            width_ratio = max_width / width
            height_ratio = max_height / height
            scaling_factor = min(width_ratio, height_ratio)

            # Calculate new dimensions based on the scaling factor
            new_width = int(width * scaling_factor)
            new_height = int(height * scaling_factor)

            # Resize the image while maintaining aspect ratio using Image.LANCZOS
            img = img.resize((new_width, new_height), Image.LANCZOS)

            # Create a white background for the final image to fit exactly 1920x1080
            final_img = Image.new("RGBA", (max_width, max_height), (255, 255, 255, 255))

            # Paste the resized image onto the white background (centered)
            paste_position = ((max_width - new_width) // 2, (max_height - new_height) // 2)
            final_img.paste(img, paste_position)

            # Resize the watermark to 1920x1080
            watermark_resized = watermark.resize((1920, 1080), Image.LANCZOS)

            # Overlay the watermark on the final image
            final_img = Image.alpha_composite(final_img, watermark_resized)

            # Convert final image back to RGB before saving to remove alpha channel
            final_img = final_img.convert("RGB")

            # Generate a unique filename for each resized image
            filename = f'resized_{uuid.uuid4().hex}.jpeg'
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            final_img.save(output_path)

            # Update the processed files mapping
            processed_files[file_hash] = filename

            resized_images.append({
                "filename": filename,
                "url": f'/uploads/{filename}'
            })

            # Add the filename to the global list for ZIP download
            resized_filenames.append(output_path)

    # Save the updated processed files mapping
    with open(processed_files_path, 'w') as f:
        json.dump(processed_files, f)

    return jsonify({"files": resized_images})

# Route to serve the uploaded files
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_file(os.path.join(app.config['UPLOAD_FOLDER'], filename), as_attachment=True)

# Route to download all files as a ZIP
@app.route('/download-all')
def download_all():
    global resized_filenames
    if not resized_filenames:
        return jsonify({"error": "No files available for download"}), 400

    # Create a ZIP file in memory
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for filepath in resized_filenames:
            filename = os.path.basename(filepath)
            zip_file.write(filepath, filename)
    zip_buffer.seek(0)

    # Send the ZIP file for download
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True, download_name='resized_images.zip')

if __name__ == '__main__':
    app.run(debug=True)
