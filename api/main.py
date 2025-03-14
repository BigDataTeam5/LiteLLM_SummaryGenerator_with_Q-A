from fastapi import FastAPI, UploadFile, File, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import os
import sys
import boto3
import fitz
import requests
import uuid
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
from fastapi import Query
MAX_FILE_SIZE_MB = 5  # Max allowed file size in MB
MAX_PAGE_COUNT = 5  # Max allowed pages
import time
import redis
import json
import asyncio
import tempfile
# Add the root directory to the Python path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

# Add the api directory to Python path as well (since PDF_Extraction_and_Markdown_Generation is in api/)
api_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(api_dir)

from api.docklingextraction import main
from logger import api_logger, pdf_logger, s3_logger, error_logger, request_logger, log_request, log_error
from llm_extractor.litellm_query_generator import MODEL_CONFIGS
import threading
from worker import main as worker_main
# Load environment variables from .env file
load_dotenv(override=True)

# AWS S3 Configuration
S3_BUCKET = os.getenv("AWS_BUCKET_NAME")
AWS_ACCESS_KEY_ID = os.getenv("AWS_SERVER_PUBLIC_KEY")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SERVER_SECRET_KEY")
AWS_REGION = os.getenv("AWS_REGION")


s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Redis client with proper error handling
redis_client = None
try:
    import redis
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        db=REDIS_DB,
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()  # Test the connection
    api_logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    api_logger.error(f"Redis connection failed: {str(e)}")
    api_logger.warning("Application will run without Redis functionality")
    # Set to None so we can check if Redis is available later
    redis_client = None

# Stream names
SUMMARY_STREAM = "summary_requests"
QUESTION_STREAM = "question_requests"
RESULT_STREAM = "llm_results"

# Create FastAPI instance
app = FastAPI(
    title="Lab Demo API",
    description="Simple FastAPI application with health check and PDF upload to S3"
)

class ScrapeRequest(BaseModel):
    url: str

# LLM Request Models
class SummaryRequest(BaseModel):
    request_id: str
    content: str
    model: str
    max_tokens: Optional[int] = 1000
    temperature: Optional[float] = 0.7

class QuestionRequest(BaseModel):
    request_id: str
    content: str
    question: str
    model: str
    max_tokens: Optional[int] = 1000
    temperature: Optional[float] = 0.7

class LLMModelsResponse(BaseModel):
    models: List[str]

class SummarizeRequest(BaseModel):
    request_id: str
    content: str
    model: str
    max_tokens: Optional[int] = 1000
    temperature: Optional[float] = 0.7
    content_type: Optional[str] = "markdown"

# In-memory results cache
llm_results = {}


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_file_details = []
#Add a middleware to log all requests
@app.middleware("http")
async def log_requests(request: Request,call_next):
    request_id = str(uuid.uuid4())
    request_path = request.url.path
    request_method = request.method
    client_host = request.client.host if request.client else "unknown"
    log_request(f"Request ID: {request_id} - {request_method} - {request_path} - Client: {client_host}")
    
    start_time  =  time.time()
    response  = await call_next(request)
    process_time = time.time() - start_time
    log_request(f"Request ID: {request_id} - Process Time: {process_time:.2f} seconds")
    return response



def check_pdf_constraints(pdf_path):
    """
    Check if the PDF meets the file size and page count constraints.
    """
    try:
        # Get file size
        pdf_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)  # Convert bytes to MB

        # Get page count
        with fitz.open(pdf_path) as pdf_doc:
            pdf_page_count = len(pdf_doc)

        if pdf_size_mb > MAX_FILE_SIZE_MB:
            error_message = f"❌ File too large: {pdf_size_mb:.2f}MB (Limit: {MAX_FILE_SIZE_MB}MB). Process stopped."
            pdf_logger.warning(error_message)
            return {"error": error_message}  # Return error instead of raising

        if pdf_page_count > MAX_PAGE_COUNT:
            error_message = f"❌ Too many pages: {pdf_page_count} pages (Limit: {MAX_PAGE_COUNT} pages). Process stopped."
            pdf_logger.warning(error_message)
            return {"error": error_message}  # Return error instead of raising

        pdf_logger.info(f"✅ PDF meets size ({pdf_size_mb:.2f}MB) and page count ({pdf_page_count} pages) limits. Proceeding with upload...")
        return {"success": True}

    except Exception as e:
        log_error(f"Failed to check PDF constraints: {str(e)}")
        return {"error": f"Failed to check PDF constraints: {str(e)}"}
    
@app.get("/")
async def root() -> Dict[str, str]:
    """
    Root endpoint with basic service information
    """
    api_logger.info("Root endpoint accessed")
    return {
        "service": "Lab Demo API",
        "version": "1.0.0",
        "documentation": "/docs"
    }
# Start the worker process on application startup
@app.on_event("startup")
async def startup_event():
    # Start the worker process in the background
    worker_thread = threading.Thread(target=start_worker_process, daemon=True)
    worker_thread.start()
    api_logger.info("LLM worker process started in background thread")

# Background task to listen for LLM results from Redis and update the cache
@app.on_event("startup")
async def start_result_listener():
    """
    Start a background task that listens for new results in the Redis stream
    and updates the in-memory cache.
    """
    # Skip if Redis isn't available
    if redis_client is None:
        api_logger.warning("Redis not available - result listener not started")
        return
    
    async def listen_for_results():
        # Create consumer group if it doesn't exist
        try:
            redis_client.xgroup_create(RESULT_STREAM, "fastapi_listeners", mkstream=True)
        except redis.exceptions.ResponseError as e:
            # Group likely already exists
            api_logger.info(f"Consumer group already exists: {str(e)}")
        except Exception as e:
            api_logger.error(f"Error creating consumer group: {str(e)}")
            return
        
        api_logger.info("Started Redis result listener")
        
        while True:
            try:
                # Your Redis processing code here
                pass
            except Exception as e:
                api_logger.error(f"Error in result listener: {str(e)}")
            
            # Wait a bit before next poll
            await asyncio.sleep(1)
    
    # Start the listener task
    asyncio.create_task(listen_for_results())


# ✅ Favicon Route
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...), service_type: str = Query("")) -> Dict[str, str]:
    """
    Uploads a PDF file to AWS S3 after checking constraints.
    """
    pdf_logger.info(f"PDF upload requested : {file.filename},Service type: {file.content_type}")
    if file.content_type != "application/pdf":
        pdf_logger.warning(f"Invalid file type attempted: {file.content_type}")
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    if not file.filename:
        pdf_logger.warning("Upload attempted with no filename")
        raise HTTPException(status_code=400, detail="Uploaded file has no name")

    if not S3_BUCKET:
        log_error("S3_BUCKET environment variable is missing")
        raise HTTPException(status_code=500, detail="S3_BUCKET environment variable is missing")
    
    temp_pdf_path = None  # Define temp path for cleanup

    try:
        # Save the uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            temp_pdf.write(file.file.read())
            temp_pdf_path = temp_pdf.name
        pdf_logger.info(f"PDF temporarily saved to: {temp_pdf_path}")

        # Check PDF constraints for only Enterprise service type
        if service_type == "Enterprise":
            pdf_logger.info(f"Checking Enterprise constraints for {file.filename}")
            constraint_check = check_pdf_constraints(temp_pdf_path)
            if "error" in constraint_check:
                pdf_logger.warning(f"PDF failed constraint check: {constraint_check['error']}")
                os.remove(temp_pdf_path)  # Cleanup temp file
                raise HTTPException(status_code=400, detail=constraint_check["error"])

        # Upload file to S3 (only if constraints are met)
        s3_key = f"RawInputs/{file.filename}"
        s3_logger.info(f"Uploading PDF to S3: {s3_key}")
        s3_client.upload_file(temp_pdf_path, S3_BUCKET, s3_key)
        s3_logger.info(f"PDF successfully uploaded to S3: s3://{S3_BUCKET}/{s3_key}")

        s3_logger.debug(f"Generated pre-signed URL for {s3_key}")
        # Cleanup: Delete the temp file after successful upload
        os.remove(temp_pdf_path)
        pdf_logger.debug(f"Temporary PDF file deleted: {temp_pdf_path}")
        # Save the file details globally
        new_file_details = {
            "filename": file.filename,
            "s3_key": s3_key,
            "upload_time": str(time.time())
        }
        latest_file_details.append(new_file_details)
        pdf_logger.info(f"File details saved for {file.filename}")
        return {"filename": file.filename, "message": "✅ PDF uploaded successfully!"}

    except NoCredentialsError:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)  # Cleanup on error
        log_error("AWS credentials not found")
        raise HTTPException(status_code=500, detail="AWS credentials not found")
    except HTTPException as e:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)  # Cleanup on error
        raise e
    except Exception as e:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)  # Cleanup on error
        log_error(f"PDF upload failed for {file.filename}", e)
        raise HTTPException(status_code=500, detail=f"❌ Upload failed: {str(e)}")
        
@app.get("/get-latest-file-url")
async def get_latest_file_url() -> Dict[str, Any]:
    """
    Retrieve the most recently uploaded file's URL, download it locally, and save the details.
    """
    api_logger.info("Fetching latest file URL")
    if not latest_file_details:
        api_logger.warning("No files have been uploaded yet")
        raise HTTPException(status_code=404, detail="No files have been uploaded yet")
    
    current_file = latest_file_details[-1]
    api_logger.info(f"Latest file: {current_file['filename']}")
    
    # Get the S3 key from stored details
    s3_key = current_file["s3_key"]
    
    try:
        # Generate a fresh pre-signed URL (the stored one might have expired)
        fresh_file_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': s3_key},
            ExpiresIn=3600  # 1 hour validity
        )
        
        # Update the URL in our stored details
        current_file["file_url"] = fresh_file_url
        s3_logger.info(f"Generated fresh pre-signed URL for {s3_key}")
        
        # Define local download path
        project_root = os.getcwd()
        downloaded_pdf_path = os.path.join(project_root, current_file["filename"])

        # Download the file using the fresh URL
        pdf_logger.info(f"Downloading file from: {fresh_file_url}")
        response = requests.get(fresh_file_url)
        response.raise_for_status()
        
        with open(downloaded_pdf_path, "wb") as pdf_file:
            pdf_file.write(response.content)
        
        pdf_logger.info(f"PDF downloaded successfully to: {downloaded_pdf_path}")
        
        # Update the local path in the global file details
        current_file["local_path"] = downloaded_pdf_path
        pdf_logger.debug(f"Updated local path in file details: {downloaded_pdf_path}")
        
    except requests.exceptions.RequestException as e:
        log_error(f"Failed to download PDF: {current_file['filename']}", e)
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {str(e)}")
    except Exception as e:
        log_error(f"Error in get_latest_file_url: {str(e)}", e)
        raise HTTPException(status_code=500, detail=f"Error retrieving file: {str(e)}")

    return current_file

@app.get("/convert-pdf-markdown")
async def convert_pdf_to_markdown_api(service_type: str = Query("Open Source")):
    """
    Uses the saved latest file details to convert the PDF into markdown using Docling.
    """
    api_logger.info(f"PDF to Markdown conversion requested using service type: {service_type}")
    try:
        if not latest_file_details:
            api_logger.warning("No file has been downloaded yet")
            raise HTTPException(status_code=404, detail="No file has been downloaded yet. Please fetch the latest file first.")

        current_file = latest_file_details[-1]
        # Extract the details from the saved data
        local_path = current_file.get("local_path")
        filename = current_file.get("filename")

        if not local_path or not filename:
            api_logger.warning("Incomplete file details")
            raise HTTPException(status_code=404, detail="Incomplete file details. Please fetch the latest file again.")

        pdf_logger.info(f"Starting Docling conversion for {filename} using {service_type} service")
        main(local_path, service_type)
        pdf_logger.info(f"Docling conversion completed for {filename}")

        return {
            "filename": filename,
            "message": "PDF successfully converted to Markdown using Docling and uploaded to S3",
            "local_path": local_path,
        }

    except Exception as e:
        log_error("Docling Markdown conversion failed", e)
        raise HTTPException(status_code=500, detail=f"Docling Markdown conversion failed: {str(e)}")
    
@app.get("/fetch-latest-markdown-urls")
async def fetch_latest_markdown_from_s3():
    """
    Fetch Markdown file URLs from the latest job-specific subfolder in S3.
    """
    api_logger.info("Fetching latest markdown URLs from S3")
    try:
        # Base folder where markdowns are stored
        s3_base_folder = "pdf_processing_pipeline/markdown_outputs/"
        s3_logger.info(f"Checking S3 folder: {s3_base_folder}")

        # Fetch all objects under markdown_outputs
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=s3_base_folder, Delimiter='/')

        if "CommonPrefixes" not in response:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown folders found in S3.")

        # Extract all job-specific subfolders
        subfolders = [prefix["Prefix"] for prefix in response["CommonPrefixes"]]
        s3_logger.info(f"Found {len(subfolders)} markdown subfolders in S3")

        if not subfolders:
            api_logger.warning("No markdown subfolders found in S3")
            raise HTTPException(status_code=404, detail="No markdown subfolders found in S3.")

        # Fetch last modified markdown file inside each subfolder
        latest_folder = None
        latest_time = None

        for folder in subfolders:
            # List files inside each subfolder
            folder_response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=folder)

            if "Contents" not in folder_response:
                continue

            # Get the latest modified file inside the folder
            for obj in folder_response["Contents"]:
                if obj["Key"].endswith(".md"):
                    last_modified = obj["LastModified"]

                    if latest_time is None or last_modified > latest_time:
                        latest_folder = folder
                        latest_time = last_modified

        if latest_folder is None:
            api_logger.warning("No markdown files found in any subfolder")
            raise HTTPException(status_code=404, detail="No markdown files found in subfolders.")

        s3_logger.info(f"Latest folder identified: {latest_folder}")

        # Fetch all markdown files inside the latest folder
        latest_folder_response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=latest_folder)
        markdown_urls = [
            f"https://{S3_BUCKET}.s3.amazonaws.com/{obj['Key']}"
            for obj in latest_folder_response["Contents"]
            if obj["Key"].endswith(".md")
        ]
        
        s3_logger.info(f"Found {len(markdown_urls)} markdown files in the latest folder")

        return {
            "message": f"Fetched Markdown files from the latest subfolder: {latest_folder}",
            "latest_folder": latest_folder,
            "markdown_files": markdown_urls
        }

    except Exception as e:
        log_error("Failed to fetch markdown URLs from S3", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch markdown files: {str(e)}")

@app.get("/fetch-latest-markdown-downloads")
async def fetch_latest_markdown_downloads():
    """
    Fetch Markdown file download links from the latest job-specific folder in S3.
    """
    api_logger.info("Fetching latest markdown URLs from S3")

    try:
        # Base S3 folder where markdowns are stored
        s3_base_folder = "pdf_processing_pipeline/markdown_outputs/"
        s3_logger.info(f"Checking S3 folder: {s3_base_folder}")


        # Fetch all job subfolders
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=s3_base_folder, Delimiter='/')

        if "CommonPrefixes" not in response:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown folders found in S3.")

        # Extract all subfolders
        subfolders = [prefix["Prefix"] for prefix in response["CommonPrefixes"]]
        s3_logger.info(f"Found {len(subfolders)} markdown subfolders in S3")

        if not subfolders:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown subfolders found in S3.")

        # Find the latest folder based on the most recently modified file
        latest_folder = None
        latest_time = None

        for folder in subfolders:
            folder_response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=folder)
            s3_logger.info(f"Checking folder: {folder}")

            if "Contents" not in folder_response:
                s3_logger.info(f"No markdown files found in folder: {folder}")
                continue

            # Check the latest file modification time inside each subfolder
            for obj in folder_response["Contents"]:
                if obj["Key"].endswith(".md"):
                    last_modified = obj["LastModified"]
                    s3_logger.info(f"Found markdown file: {obj['Key']} - Last modified: {last_modified}")

                    if latest_time is None or last_modified > latest_time:
                        latest_folder = folder
                        latest_time = last_modified
                        s3_logger.info(f"Latest folder updated: {latest_folder}")

        if latest_folder is None:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown files found in subfolders.")

        # ✅ List all Markdown files inside the latest folder
        latest_folder_response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=latest_folder)
        markdown_files = [
            obj["Key"] for obj in latest_folder_response["Contents"] if obj["Key"].endswith(".md")
        ]

        if not markdown_files:
            api_logger.warning("No markdown files found in the latest folder")
            raise HTTPException(status_code=404, detail="No markdown files available for download.")

        # ✅ Generate public or pre-signed download URLs for the markdown files
        markdown_download_links = []
        for file_key in markdown_files:
            s3_logger.info(f"Generating download link for: {file_key}")
            # ✅ Option 1: Use pre-signed URL for private files (recommended for security)
            download_url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": file_key},
                ExpiresIn=3600 
            )
            markdown_download_links.append({
                "file_name": file_key.split("/")[-1],
                "download_url": download_url
            })
            s3_logger.info(f"Download link generated for: {file_key}")

        return {
            "message": f"Fetched Markdown downloads from the latest subfolder: {latest_folder}",
            "latest_folder": latest_folder,
            "markdown_downloads": markdown_download_links
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch markdown downloads: {str(e)}")
    
@app.get("/list-image-ref-markdowns")
async def list_image_ref_markdowns():
    """
    Fetch all Markdown files with 'image-ref' suffix from all subfolders in S3 and generate download links.
    """
    api_logger.info("Fetching image-ref markdown files from all folders in S3")

    try:
        # Base S3 folder where markdowns are stored
        s3_base_folder = "pdf_processing_pipeline/markdown_outputs/"
        s3_logger.info(f"Checking S3 base folder: {s3_base_folder}")

        # Fetch all job subfolders
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=s3_base_folder, Delimiter='/')

        if "CommonPrefixes" not in response:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown folders found in S3.")

        # Extract all subfolders
        subfolders = [prefix["Prefix"] for prefix in response["CommonPrefixes"]]
        s3_logger.info(f"Found {len(subfolders)} markdown subfolders in S3")

        if not subfolders:
            api_logger.warning("No markdown folders found in S3")
            raise HTTPException(status_code=404, detail="No markdown subfolders found in S3.")

        # Collect all image-ref markdown files from all folders
        image_md_files = []

        for folder in subfolders:
            s3_logger.info(f"Searching for image-ref markdowns in folder: {folder}")
            folder_response = s3_client.list_objects_v2(Bucket=S3_BUCKET, Prefix=folder)
            
            if "Contents" not in folder_response:
                s3_logger.info(f"No files found in folder: {folder}")
                continue
            
            # Filter for markdown files with image-ref in their name
            for obj in folder_response["Contents"]:
                file_key = obj["Key"]
                file_name = file_key.split("/")[-1]
                
                if file_key.endswith(".md") and "-with-images." in file_name:
                    s3_logger.info(f"Found markdown with images: {file_key}")
                    
                    # Generate pre-signed URL for the file
                    download_url = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": S3_BUCKET, "Key": file_key},
                        ExpiresIn=3600  # 1 hour validity
                    )
                    
                    # Add to our collection
                    image_md_files.append({
                        "folder": folder,
                        "file_name": file_name,
                        "file_key": file_key,
                        "download_url": download_url,
                        "last_modified": obj["LastModified"].isoformat()
                    })
                    
                    s3_logger.info(f"Generated download link for: {file_key}")

        if not image_md_files:
            api_logger.warning("No image-ref markdown files found in any folder")
            raise HTTPException(status_code=404, detail="No image-ref markdown files found.")

        # Sort by last modified date (newest first)
        image_md_files.sort(key=lambda x: x["last_modified"], reverse=True)
        
        return {
            "message": f"Found {len(image_md_files)} image-ref markdown files across {len(subfolders)} folders",
            "file_count": len(image_md_files),
            "folder_count": len(subfolders),
            "image_ref_markdowns": image_md_files
        }

    except Exception as e:
        log_error("Failed to fetch image-ref markdown files", e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch image-ref markdown files: {str(e)}")
# llm endpoints starts here
def start_worker_process():
    """
    Start the LLM worker process using asyncio in a separate thread
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(worker_main())
    loop.close()

@app.post("/summarize", status_code=202)
async def summarize_content(request: SummaryRequest):
    """
    Submit content for summarization by an LLM through Redis streams.
    Returns a 202 Accepted response with the request ID for polling results.
    """
    api_logger.info(f"Summary request received for model: {request.model}")
    try:
        # Add message to Redis summary stream
        data = {
            "request_id": request.request_id,
            "content": request.content,
            "model": request.model,
            "max_tokens": str(request.max_tokens),
            "temperature": str(request.temperature),
            "timestamp": str(time.time())
        }
        
        # Push to Redis stream
        redis_client.xadd(SUMMARY_STREAM, data)
        api_logger.info(f"Summary request {request.request_id} pushed to Redis stream")
        
        return {"request_id": request.request_id, "status": "processing"}
    except Exception as e:
        log_error(f"Failed to submit summary request", e)
        raise HTTPException(status_code=500, detail=f"Failed to process request: {str(e)}")

@app.post("/ask-question", status_code=202)
async def ask_question(request: QuestionRequest):
    """
    Submit content and a question for an LLM to answer through Redis streams.
    Returns a 202 Accepted response with the request ID for polling results.
    """
    api_logger.info(f"Question request received for model: {request.model}")
    try:
        # Add message to Redis question stream
        data = {
            "request_id": request.request_id,
            "content": request.content,
            "question": request.question,
            "model": request.model,
            "max_tokens": str(request.max_tokens),
            "temperature": str(request.temperature),
            "timestamp": str(time.time())
        }
        
        # Push to Redis stream
        redis_client.xadd(QUESTION_STREAM, data)
        api_logger.info(f"Question request {request.request_id} pushed to Redis stream")
        
        return {"request_id": request.request_id, "status": "processing"}
    except Exception as e:
        log_error(f"Failed to submit question request", e)
        raise HTTPException(status_code=500, detail=f"Failed to process request: {str(e)}")


@app.on_event("startup")
async def create_redis_streams():
    """Ensure all required Redis streams exist"""
    try:
        # Skip if Redis isn't available
        if redis_client is None:
            api_logger.warning("Redis not available - skipping stream creation")
            return
            
        # Create streams if they don't exist (add a dummy message that can be deleted later)
        for stream in [SUMMARY_STREAM, QUESTION_STREAM, RESULT_STREAM]:
            # Check if stream exists
            if not redis_client.exists(stream):
                api_logger.info(f"Creating Redis stream: {stream}")
                # Add a dummy message that will be processed and removed
                redis_client.xadd(stream, {"init": "init"}, maxlen=10)
        api_logger.info("All required Redis streams initialized")
    except Exception as e:
        log_error(f"Error initializing Redis streams", e)
        
@app.get("/get-llm-result/{request_id}")
async def get_llm_result(request_id: str):
    """
    Check if results for a given request ID are available.
    This endpoint polls Redis for results from LLM processing.
    """
    api_logger.info(f"Checking for results for request: {request_id}")
    try:
        # Check the in-memory cache first
        if request_id in llm_results:
            result = llm_results[request_id]
            api_logger.info(f"Result found in cache for request: {request_id}")
            return {"request_id": request_id, "status": "completed", **result}
        
        # If not in cache, query Redis stream for results
        # Get all messages from the result stream
        messages = redis_client.xread({RESULT_STREAM: '0'}, count=100)
        
        if not messages:
            api_logger.info(f"No results found yet for request: {request_id}")
            return {"request_id": request_id, "status": "processing"}
        
        # Find the result matching our request_id
        for stream_name, stream_messages in messages:
            for message_id, data in stream_messages:
                if data.get("request_id") == request_id:
                    api_logger.info(f"Result found in Redis for request: {request_id}")
                    
                    # If there was an error
                    if "error" in data:
                        return {
                            "request_id": request_id,
                            "status": "error",
                            "error": data["error"]
                        }
                    
                    # Parse the data properly
                    result_data = {}
                    for key, value in data.items():
                        if key != "request_id":  # We add this separately
                            # Handle usage data specially - convert from JSON string back to dict
                            if key == "usage" and value.startswith("{"):
                                try:
                                    result_data[key] = json.loads(value)
                                except json.JSONDecodeError:
                                    result_data[key] = value
                            else:
                                result_data[key] = value
                    
                    # Cache the result
                    llm_results[request_id] = result_data
                    
                    # Return the result
                    return {
                        "request_id": request_id, 
                        "status": "completed",
                        **result_data
                    }
        
        # No result found yet
        return {"request_id": request_id, "status": "processing"}
    except Exception as e:
        log_error(f"Error retrieving results for request: {request_id}", e)
        return {
            "request_id": request_id,
            "status": "error",
            "error": str(e)
        }

@app.get("/llm/models", response_model=LLMModelsResponse)
async def list_available_models():
    """
    Returns a list of available LLM models that can be used for summarization and Q&A
    """
    try:
        models = list(MODEL_CONFIGS.keys())
        api_logger.info(f"Retrieved {len(models)} available LLM models")
        return {"models": models}
    except Exception as e:
        log_error("Failed to retrieve available models", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve available models: {str(e)}")

@app.get("/llm/health")
async def check_llm_health():
    """
    Check if the LLM worker process is running and Redis streams are operational
    """
    try:
        # Check Redis connection
        redis_ping = redis_client.ping()
        
        # Check if worker streams exist
        summary_exists = redis_client.exists(SUMMARY_STREAM)
        question_exists = redis_client.exists(QUESTION_STREAM)
        result_exists = redis_client.exists(RESULT_STREAM)
        
        return {
            "redis_connected": bool(redis_ping),
            "streams": {
                "summary_stream": bool(summary_exists),
                "question_stream": bool(question_exists),
                "result_stream": bool(result_exists)
            },
            "status": "healthy" if redis_ping else "unhealthy"
        }
    except Exception as e:
        log_error("LLM health check failed", e)
        return {
            "status": "unhealthy",
            "error": str(e)
        }