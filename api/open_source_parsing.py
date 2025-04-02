import os
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

