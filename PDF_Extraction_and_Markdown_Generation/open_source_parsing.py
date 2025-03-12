import os
import fitz  # PyMuPDF
import camelot
import requests
import boto3
import re
from dotenv import load_dotenv
from pathlib import Path
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()

# AWS S3 Configuration
session = boto3.Session(
    aws_access_key_id=os.getenv('AWS_SERVER_PUBLIC_KEY'),
    aws_secret_access_key=os.getenv('AWS_SERVER_SECRET_KEY'),
)
s3 = session.client('s3', region_name=os.getenv('AWS_REGION'))
bucket_name = os.getenv('AWS_BUCKET_NAME')

def check_file_exists_in_s3(object_name):
    """Check if a file exists in S3."""
    try:
        s3.head_object(Bucket=bucket_name, Key=object_name)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise

def get_versioned_object_name(base_object_name):
    """Generate a versioned object name for S3."""
    # Extract base name and extension
    path = Path(base_object_name)
    folder = str(path.parent)
    name = path.stem
    ext = path.suffix
    
    # Check if name already has a version suffix (v1, v2, etc.)
    version_match = re.search(r'_v(\d+)$', name)
    if version_match:
        # Extract current version number and base name
        current_version = int(version_match.group(1))
        base_name = name[:version_match.start()]
        new_version = current_version + 1
        new_name = f"{base_name}_v{new_version}"
    else:
        # No version suffix, add v1
        new_name = f"{name}_v1"
    
    # Create new object name
    if folder and folder != '.':
        return f"{folder}/{new_name}{ext}"
    else:
        return f"{new_name}{ext}"

def upload_pdf_to_s3(file_path, object_name):
    """Upload a PDF to S3 with version control."""
    try:
        # Check if file exists in S3
        if check_file_exists_in_s3(object_name):
            # Generate versioned object name
            object_name = get_versioned_object_name(object_name)
        
        # Upload file
        s3.upload_file(file_path, bucket_name, object_name)
        return {
            "status": "success",
            "message": f"Uploaded {file_path} to s3://{bucket_name}/{object_name}",
            "object_name": object_name
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error uploading file {file_path}: {e}",
            "object_name": None
        }

def upload_file_to_s3(file_path, object_name):
    """Uploads a file to S3."""
    try:
        s3.upload_file(file_path, bucket_name, object_name)
        return f"Uploaded {file_path} to s3://{bucket_name}/{object_name}"
    except Exception as e:
        return f"Error uploading file {file_path}: {e}"

def download_pdf(url, output_path):
    """Download PDF from a URL and save to local storage."""
    response = requests.get(url)
    if response.status_code == 200:
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(response.content)
        return f"PDF downloaded successfully: {output_path}"
    else:
        raise Exception(f"Failed to download PDF. Status code: {response.status_code}")

def upload_pdf_to_raw_input(file_path):
    """Upload PDF to the raw input folder in S3 with version control."""
    pdf_filename = os.path.basename(file_path)
    s3_path = f"rawinput/{pdf_filename}"
    return upload_pdf_to_s3(file_path, s3_path)

def extract_text_from_pdf(file_path, base_output_folder):
    """Extract text from PDF and upload to S3."""
    logs = []
    
    # Create job-specific folder based on PDF filename
    pdf_filename = Path(file_path).stem
    job_folder = pdf_filename
    output_folder = os.path.join(base_output_folder, job_folder)
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Define S3 folder path
    s3_folder = f"pdf_processing_pipeline/pdf_os_pipeline/parsed_data/{job_folder}/"
    
    with fitz.open(file_path) as pdf_document:
        for page_num in range(len(pdf_document)):
            text = pdf_document[page_num].get_text()
            text_filename = os.path.join(output_folder, f"page_{page_num + 1}_text.txt")
            with open(text_filename, "w", encoding="utf-8") as text_file:
                text_file.write(text)
            logs.append(upload_file_to_s3(text_filename, f"{s3_folder}{os.path.basename(text_filename)}"))
    return logs

def extract_images_from_pdf(file_path, base_output_folder):
    """Extract images from PDF and upload to S3."""
    logs = []
    
    # Create job-specific folder based on PDF filename
    pdf_filename = Path(file_path).stem
    job_folder = pdf_filename
    output_folder = os.path.join(base_output_folder, job_folder)
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Define S3 folder path
    s3_folder = f"pdf_processing_pipeline/pdf_os_pipeline/parsed_data/{job_folder}/"
    
    pdf_document = fitz.open(file_path)
    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            if base_image is None or "image" not in base_image:
                continue
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_filename = os.path.join(output_folder, f"page_{page_num + 1}_img_{img_index + 1}.{image_ext}")
            with open(image_filename, "wb") as img_file:
                img_file.write(image_bytes)
            logs.append(upload_file_to_s3(image_filename, f"{s3_folder}{os.path.basename(image_filename)}"))
    return logs

def extract_tables_from_pdf(file_path, base_output_folder):
    """Extract tables from PDF and upload to S3."""
    logs = []
    
    # Create job-specific folder based on PDF filename
    pdf_filename = Path(file_path).stem
    job_folder = pdf_filename
    output_folder = os.path.join(base_output_folder, job_folder)
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Define S3 folder path
    s3_folder = f"pdf_processing_pipeline/pdf_os_pipeline/parsed_data/{job_folder}/"
    
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    for table in tables:
        if table.parsing_report['accuracy'] >= 80:
            table_filename = os.path.join(output_folder, f"page_{table.page}_table.csv")
            table.to_csv(table_filename)
            logs.append(upload_file_to_s3(table_filename, f"{s3_folder}{os.path.basename(table_filename)}"))
    return logs

def extract_lists_from_pdf(file_path, base_output_folder):
    """Extract lists from PDF and upload to S3."""
    logs = []
    
    # Create job-specific folder based on PDF filename
    pdf_filename = Path(file_path).stem
    job_folder = pdf_filename
    output_folder = os.path.join(base_output_folder, job_folder)
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Define S3 folder path
    s3_folder = f"pdf_processing_pipeline/pdf_os_pipeline/parsed_data/{job_folder}/"
    
    with fitz.open(file_path) as pdf_document:
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            text = page.get_text()
            list_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(('-', '*', '•', '○'))]
            if list_lines:
                list_filename = os.path.join(output_folder, f"page_{page_num + 1}_lists.txt")
                with open(list_filename, "w", encoding="utf-8") as list_file:
                    list_file.write("\n".join(list_lines))
                logs.append(upload_file_to_s3(list_filename, f"{s3_folder}{os.path.basename(list_filename)}"))
    return logs

def extract_all_from_pdf(file_path, base_output_folder):
    """Extract all data from a PDF and upload to S3."""
    logs = []
    
    # Upload PDF to raw input folder with versioning
    upload_result = upload_pdf_to_raw_input(file_path)
    logs.append(upload_result["message"])
    
    # Get the filename possibly with version suffix
    if upload_result["status"] == "success" and upload_result["object_name"]:
        s3_object_name = upload_result["object_name"]
        # Extract the versioned filename from the S3 path for our job folder
        pdf_filename = Path(s3_object_name).stem
    else:
        # Fallback to original filename if upload failed
        pdf_filename = Path(file_path).stem
    
    # Create job folder based on possibly versioned PDF name
    job_folder = pdf_filename
    output_folder = os.path.join(base_output_folder, job_folder)
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    logs += extract_text_from_pdf(file_path, base_output_folder)
    logs += extract_images_from_pdf(file_path, base_output_folder)
    logs += extract_tables_from_pdf(file_path, base_output_folder)
    logs += extract_lists_from_pdf(file_path, base_output_folder)
    return logs

if __name__ == "__main__":
    # Example usage
    pdf_url = "https://arxiv.org/pdf/2408.09869"
    pdf_filename = "arxiv_paper.pdf"
    download_pdf(pdf_url, pdf_filename)
    extract_all_from_pdf(pdf_filename, "output")