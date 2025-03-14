import streamlit as st
import requests
import time
import sys
import os
import json
import uuid
sys.path.append("LLM_Interactor")
# from logger import api_logger

# Streamlit UI
st.set_page_config(page_title="PDF-to-LLM Assistant", layout="wide")

# Initialize session state variables if they do not exist
if "file_uploaded" not in st.session_state:
    st.session_state.file_uploaded = False
if "markdown_ready" not in st.session_state:
    st.session_state.markdown_ready = False
if "show_pdf_uploader" not in st.session_state:
    st.session_state.show_pdf_uploader = False
if "show_url_input" not in st.session_state:
    st.session_state.show_url_input = False
# Initialize session state for markdown history
if "markdown_history" not in st.session_state:
    st.session_state.markdown_history = []  # To store history of markdown files
if "selected_markdown_content" not in st.session_state:
    st.session_state.selected_markdown_content = None
if "selected_markdown_name" not in st.session_state:
    st.session_state.selected_markdown_name = None
# Initialize session state for LLM responses
if "summary_result" not in st.session_state:
    st.session_state.summary_result = None
if "question_result" not in st.session_state:
    st.session_state.question_result = None
if "processing_summary" not in st.session_state:
    st.session_state.processing_summary = False
if "processing_question" not in st.session_state:
    st.session_state.processing_question = False
if "text_summary_result" not in st.session_state:
    st.session_state.text_summary_result = None
if "processing_text_summary" not in st.session_state:
    st.session_state.processing_text_summary = False

# FastAPI Base URL - Make it configurable with environment variable support
if "fastapi_url" not in st.session_state:
    # Get the FastAPI URL from environment variable if available, else use default
    default_url = os.environ.get("FASTAPI_URL", "http://localhost:8080")
    st.session_state.fastapi_url = default_url
if "api_connected" not in st.session_state:
    st.session_state.api_connected = False

# Define function to update API endpoints based on the configured URL
def update_api_endpoints():
    base_url = st.session_state.fastapi_url
    
    # API Endpoints
    st.session_state.UPLOAD_PDF_API = f"{base_url}/upload-pdf"
    st.session_state.LATEST_FILE_API = f"{base_url}/get-latest-file-url"
    st.session_state.PARSE_PDF_API = f"{base_url}/parse-pdf"
    st.session_state.PARSE_PDF_AZURE_API = f"{base_url}/parse-pdf-azure"
    st.session_state.CONVERT_MARKDOWN_API = f"{base_url}/convert-pdf-markdown"
    st.session_state.FETCH_MARKDOWN_API = f"{base_url}/fetch-latest-markdown-urls"
    st.session_state.FETCH_DOWNLOADABLE_MARKDOWN_API = f"{base_url}/fetch-latest-markdown-downloads"
    st.session_state.FETCH_MARKDOWN_HISTORY = f"{base_url}/list-image-ref-markdowns"
    st.session_state.SUMMARIZE_API = f"{base_url}/summarize"
    st.session_state.ASK_QUESTION_API = f"{base_url}/ask-question"
    st.session_state.GET_LLM_RESULT_API = f"{base_url}/get-llm-result"
    st.session_state.LLM_MODELS_API = f"{base_url}/llm/models"
    st.session_state.LLM_HEALTH_API = f"{base_url}/llm/health"

# Initial setup of API endpoints
update_api_endpoints()

# Function to test API connection - Add support for potential backend health endpoints
def test_api_connection():
    try:
        # Try to connect to the root endpoint first
        response = requests.get(f"{st.session_state.fastapi_url}/", timeout=5)
        if response.status_code == 200:
            st.session_state.api_connected = True
            return True, "Connection successful!"
        
        # If root fails, try the health endpoint
        response = requests.get(f"{st.session_state.fastapi_url}/health", timeout=5)
        if response.status_code == 200:
            st.session_state.api_connected = True
            return True, "Connection successful via health endpoint!"
            
        st.session_state.api_connected = False
        return False, f"API responded with status code: {response.status_code}"
    except requests.exceptions.ConnectionError:
        st.session_state.api_connected = False
        return False, f"Connection error: Could not connect to the FastAPI server at {st.session_state.fastapi_url}. Please check the URL and ensure the server is running."
    except requests.exceptions.Timeout:
        st.session_state.api_connected = False
        return False, "Connection timeout: The request timed out. Server might be overloaded or unavailable."
    except Exception as e:
        st.session_state.api_connected = False
        return False, f"Unexpected error: {str(e)}"

# Function to Upload File to S3 - With improved error handling
def upload_pdf(file):
    try:
        files = {"file": (file.name, file.getvalue(), "application/pdf")}
        with st.spinner("📤 Uploading PDF... Please wait."):
            service_type = st.session_state.get("service_type", None)
            response = requests.post(st.session_state.UPLOAD_PDF_API, files=files, params={"service_type": service_type})

        if response.status_code == 200:
            st.session_state.file_uploaded = True
            return response.json()
        else:
            try:
                error_detail = response.json().get("detail", f"Upload failed: {response.status_code}")
            except ValueError:
                error_detail = f"Upload failed with status {response.status_code}: {response.text}"
            st.error(f"Error: {error_detail}")
            return {"error": error_detail}
    except requests.RequestException as e:
        st.error(f"Request Exception: {str(e)}")
        return {"error": str(e)}
            
# Function to Convert PDF to Markdown (With Progress Bar)
def convert_to_markdown():
    with st.spinner("⏳ Converting PDF to Markdown... Please wait."):
        progress_bar = st.progress(0)

        try:
            for i in range(10):  # Simulate progress while waiting
                time.sleep(1)
                progress_bar.progress((i + 1) * 10)

            service_type = st.session_state.get("service_type", None)
            # Step 1: Get Latest File URL
            response_latest = requests.get(st.session_state.LATEST_FILE_API,params={"service_type": service_type})
            if response_latest.status_code != 200:
                progress_bar.empty()
                return {"error": f"❌ Failed to fetch latest file URL: {response_latest.text}"}

            # Step 2: Convert PDF to Markdown
            response = requests.get(st.session_state.CONVERT_MARKDOWN_API)
            if response.status_code == 200:
                st.session_state.markdown_ready = True
                progress_bar.empty()
                # Call fetch_markdown_history after success conversion
                fetch_markdown_history()
                return {"message": "✅ Markdown Conversion Completed! Click View to see results."}
            else:
                progress_bar.empty()
                return {"error": f"❌ Markdown conversion failed! Response: {response.text}"}

        except requests.exceptions.RequestException as e:
            progress_bar.empty()
            return {"error": f"⚠️ API Request Failed: {str(e)}"}
# Function to Fetch Markdown File from S3
def fetch_markdown():
    with st.spinner("⏳ Fetching Markdown File from S3... Please wait."):
        progress_bar = st.progress(0)  # Initialize progress bar

        try:
            for i in range(10):  # Simulate progress
                time.sleep(0.5)
                progress_bar.progress((i + 1) * 10)

            response = requests.get(st.session_state.FETCH_MARKDOWN_API)
            if response.status_code == 200:
                markdown_files = response.json().get("files", [])
                progress_bar.empty()
                if markdown_files:
                    return {"markdown_file": markdown_files[-1]}  # Show latest markdown file
                else:
                    return {"error": "No markdown file found!"}
            else:
                progress_bar.empty()
                return {"error": "Failed to fetch markdown files!"}

        except requests.RequestException as e:
            progress_bar.empty()
            return {"error": str(e)}
# Function to Fetch Downloadable Markdown Files from S3
def fetch_downloadable_markdown():
    """
    Fetch Markdown file download links from the latest job-specific folder in S3.
    """
    try:
        with st.spinner("⏳ Fetching Markdown download links... Please wait."):
            response = requests.get(st.session_state.FETCH_DOWNLOADABLE_MARKDOWN_API)
        
        if response.status_code == 200:
            markdown_data = response.json()
            return markdown_data.get("markdown_downloads", [])
        else:
            return {"error": f"Failed to fetch markdown downloads! Response: {response.text}"}

    except requests.RequestException as e:
        return {"error": str(e)}
# Function to fetch image-ref markdown history
def fetch_markdown_history():
    """
    Fetch all image-ref markdown files from S3 across all folders.
    """
    try:
        with st.spinner("⏳ Fetching markdown history... Please wait."):
            response = requests.get(st.session_state.FETCH_MARKDOWN_HISTORY)
            # Debug: Print API response
            print(f"API Response Status: {response.status_code}")
            print(f"API Response URL: {st.session_state.FETCH_MARKDOWN_HISTORY}")
        
        if response.status_code == 200:
            markdown_data = response.json()
            print(f"Markdown Data: {markdown_data}")  # Debug print
            
            # Process the markdown files for display in sidebar history
            history_items = []
            
            if "image_ref_markdowns" not in markdown_data:
                print(f"Expected keys not found. Available keys: {markdown_data.keys()}")
                return []
            
            for item in markdown_data.get("image_ref_markdowns", []):
                try:
                    display_name = item["file_name"].replace("-with-image-refs", "").replace(".md", "")
                    history_items.append({
                        "label": display_name,
                        "url": item["download_url"],
                        "folder": item["folder"],
                        "last_modified": item["last_modified"]
                    })
                except KeyError as e:
                    print(f"Error processing item: {e}, Item data: {item}")
                    continue
            
            # Update session state with the history items
            if history_items:
                st.session_state.markdown_history = history_items
                print(f"Updated history with {len(history_items)} items")
            return history_items
        else:
            print(f"API Error: {response.status_code}, {response.text}")
            st.error(f"Failed to fetch markdown history! Response: {response.text}")
            return []

    except requests.RequestException as e:
        print(f"Request Exception: {e}")
        st.error(f"Request error: {str(e)}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        st.error(f"Unexpected error: {str(e)}")
        return []
    
if not st.session_state.markdown_history:
    fetch_markdown_history()

# Function to fetch available LLM models from API
def fetch_available_models():
    """Fetch available LLM models from the backend API"""
    try:
        response = requests.get(st.session_state.LLM_MODELS_API)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return models
        else:
            st.warning(f"Could not fetch available models: {response.status_code}")
            return ["gemini"]  # Default fallback model
    except Exception as e:
        st.warning(f"Error fetching models: {str(e)}")
        return ["gemini"]  # Default fallback model

# Function to check LLM health
def check_llm_health():
    """Check if the LLM backend is healthy"""
    try:
        response = requests.get(st.session_state.LLM_HEALTH_API)
        if response.status_code == 200:
            return response.json()
        else:
            return {"status": "unhealthy", "error": f"Status code: {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

# Enhanced function to submit summarization request - Streamlined for markdown content
def submit_summarization(content, model):
    """Submit markdown content to be summarized by the selected LLM model"""
    try:
        with st.spinner("⏳ Generating summary with LLM... This may take a moment."):
            # Generate a unique request ID
            request_id = f"summary_{uuid.uuid4()}"

            # Submit the summarization request with markdown content
            response = requests.post(
                st.session_state.SUMMARIZE_API,
                json={
                    "request_id": request_id,
                    "content": content,
                    "model": model,
                    "max_tokens": 1500,
                    "temperature": 0.5,
                    "content_type": "markdown"  # Explicitly mark as markdown content
                },
                timeout=30
            )

            if response.status_code == 202:
                st.session_state.processing_summary = True
                st.info("Processing markdown content...")
                
                # Start polling for results
                result = poll_for_llm_result(request_id)
                if result and "error" not in result:
                    st.session_state.summary_result = result
                    return result
                else:
                    st.error(f"Error getting summary: {result.get('error', 'Unknown error')}")
                    return None
            else:
                st.error(f"Failed to submit summary request: {response.text}")
                return None
    except Exception as e:
        st.error(f"Error in summarization: {str(e)}")
        return None

# Enhanced function to submit question to LLM - Updated to handle markdown content
def submit_question(content, question, model):
    """Submit markdown content and question to be answered by the selected LLM model"""
    try:
        with st.spinner("⏳ Processing your question with LLM... This may take a moment."):
            # Generate a unique request ID
            request_id = f"question_{uuid.uuid4()}"

            # Submit the question request with markdown content
            response = requests.post(
                st.session_state.ASK_QUESTION_API,
                json={
                    "request_id": request_id,
                    "content": content,
                    "question": question,
                    "model": model,
                    "max_tokens": 1500,
                    "temperature": 0.5,
                    "content_type": "markdown"  # Explicitly mark as markdown content
                },
                timeout=30
            )

            if response.status_code == 202:
                st.session_state.processing_question = True
                st.info("Processing your question...")

                # Start polling for results
                result = poll_for_llm_result(request_id)
                if result and "error" not in result:
                    st.session_state.question_result = result
                    return result
                else:
                    st.error(f"Error getting answer: {result.get('error', 'Unknown error')}")
                    return None
            else:
                st.error(f"Failed to submit question: {response.text}")
                return None
    except Exception as e:
        st.error(f"Error in question processing: {str(e)}")
        return None

# Improved polling function with progress bar and timeout
def poll_for_llm_result(job_id, max_retries=15, interval=2):
    """Poll for LLM result with a progress bar and better timeout handling"""
    retries = 0
    
    # Create a progress bar
    progress_text = "Waiting for LLM to process your request..."
    progress_bar = st.progress(0)
    
    while retries < max_retries:
        try:
            # Calculate progress percentage
            progress = min(retries / max_retries, 0.95)  # Cap at 95% until complete
            progress_bar.progress(progress)
            
            # Check result status
            response = requests.get(
                f"{st.session_state.GET_LLM_RESULT_API}/{job_id}",
                timeout=10
            )
            
            if response.status_code == 200:
                result_data = response.json()
                status = result_data.get("status")
                
                if status == "completed":
                    progress_bar.progress(1.0)  # Complete the progress bar
                    time.sleep(0.5)  # Brief pause to show completed progress
                    progress_bar.empty()  # Remove the progress bar
                    return result_data
                    
                elif status == "failed":
                    progress_bar.empty()
                    st.error(f"LLM processing failed: {result_data.get('error', 'Unknown error')}")
                    return None
                    
                # Still processing
                st.info(f"Processing... {int(progress*100)}% (Attempt {retries+1}/{max_retries})")
            
            elif response.status_code == 404:
                # Job not found
                progress_bar.empty()
                st.error("Job not found. It may have expired or been deleted.")
                return None
                
            else:
                # Other error
                st.warning(f"Unexpected response while checking status: {response.status_code}")
            
            # Wait before next retry
            retries += 1
            time.sleep(interval)
            
        except Exception as e:
            progress_bar.empty()
            st.error(f"Error while polling for result: {str(e)}")
            return None
    
    # If we get here, we've exceeded max retries
    progress_bar.empty()
    st.error(f"Timed out waiting for LLM response after {max_retries * interval} seconds. The document may be too large or complex.")
    return None

# Fetch models at startup
if "available_models" not in st.session_state:
    st.session_state.available_models = fetch_available_models()

# Sidebar UI
with st.sidebar:
    st.subheader("API Configuration")
    
    # API URL configuration
    api_url = st.text_input("FastAPI URL", value=st.session_state.fastapi_url)
    
    if api_url != st.session_state.fastapi_url:
        st.session_state.fastapi_url = api_url
        update_api_endpoints()
        st.session_state.api_connected = False
    
    # Test connection button
    if st.button("Test Connection"):
        success, message = test_api_connection()
        if success:
            st.success(message)
        else:
            st.error(message)
    
    # Display connection status
    if st.session_state.api_connected:
        st.success("✅ Connected to FastAPI")
    else:
        st.warning("❌ Not connected to FastAPI")
    
    st.divider()
    
    st.subheader("Select Options")

    # Dropdown for processing type
    processing_type = st.selectbox("Processing Type:", ["Select an option", "PDF Extraction"], index=0)
    st.session_state.processing_type = processing_type

    # Dropdown for service type
    service_type = st.selectbox("Service Type:", ["Select Service", "Open Source", "Enterprise"], index=0)
    st.session_state.service_type = service_type

    # Enhanced dropdown for selecting LLM model using available models from API
    available_models = ["Select Model"] + st.session_state.available_models
    llm_model = st.selectbox("Select LLM Model:", available_models, index=0)
    st.session_state.llm_model = llm_model

    # Add LLM health check indicator
    if st.session_state.llm_model != "Select Model":
        with st.expander("LLM Service Health"):
            health_status = check_llm_health()
            if health_status.get("status") == "healthy":
                st.success("✅ LLM Service is online")
                st.json(health_status.get("streams", {}))
            else:
                st.error(f"❌ LLM Service issues: {health_status.get('error', 'Unknown')}")

 # Next button
    if st.button("Next"):
        if processing_type == "Select an option" or service_type == "Select Service":
            st.error("Please select both Processing Type and Service Type.")
        else:
            # Clear any selected markdown when switching to PDF extraction mode
            st.session_state.selected_markdown_content = None
            st.session_state.selected_markdown_name = None
            st.session_state.next_clicked = True
            st.success("Processing Type and Service Type selected successfully.")
            st.rerun()  # Force a rerun to update the UI
        # Add custom CSS for ChatGPT-like sidebar buttons
    st.markdown("""
    <style>
    .chat-button {
        display: block;
        width: 100%;
        border: none;
        background-color: transparent;
        padding: 10px 15px;
        text-align: left;
        cursor: pointer;
        border-radius: 5px;
        margin-bottom: 5px;
        color: #444;
        font-size: 14px;
        transition: background-color 0.3s;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
    }
    .chat-button:hover {
        background-color: rgba(0,0,0,0.05);
    }
    .chat-active {
        background-color: rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)

    st.subheader("📑 Markdown History")
    # Show markdown history items with ChatGPT-like styling
    history_container = st.container()
    with history_container:
        if not st.session_state.markdown_history:
            st.info("No markdown history available")
        else:
            for idx, markdown in enumerate(st.session_state.markdown_history):
                # Create ChatGPT-like buttons with HTML
                button_class = "chat-button"
                if "selected_markdown_name" in st.session_state and st.session_state.selected_markdown_name == markdown["label"]:
                    button_class += " chat-active"
                
                if st.button(markdown["label"], key=f"history_{idx}", use_container_width=True):
                    try:
                        content = requests.get(markdown["url"]).text
                        st.session_state.selected_markdown_content = content
                        st.session_state.selected_markdown_name = markdown["label"]
                        st.session_state.markdown_ready = True
                        st.session_state.next_clicked = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error loading markdown: {str(e)}")

# Main Page Logic
st.title("📄 LiteLLM Summary Generator and AI Assistant")

# Check if API is connected before allowing operations
if not st.session_state.api_connected:
    st.warning("⚠️ Not connected to the FastAPI backend. Please configure the correct API URL in the sidebar and test the connection.")
    
    # Add a quick troubleshooting guide
    with st.expander("Troubleshooting Connection Issues"):
        st.markdown("""
        ### Common Connection Issues:
        
        1. **Incorrect URL**: Ensure the URL is correct and includes the protocol (http/https)
        2. **FastAPI server not running**: Make sure your FastAPI server is running
        3. **Network issues**: If running locally, try using `localhost` or `127.0.0.1`
        4. **CORS issues**: If running in different domains, check CORS configuration in FastAPI
        5. **Port conflicts**: Make sure the port number matches your FastAPI configuration
        
        Try testing with direct URL access in your browser to verify the service is available.
        """)
else:
    # Only continue with the rest of the app if connected
    if st.session_state.get("selected_markdown_content", None):
        st.image("images/summary_generator.png", use_container_width=True)
        col1, col2 =  st.columns([1, 0.3])
        with col1:
            if st.button("Back to Main Menu"):
                st.session_state.selected_markdown_content = None
                st.session_state.selected_markdown_name = None
                st.session_state.markdown_ready = False
                st.session_state.next_clicked = False
                st.session_state.summary_result = None
                st.session_state.question_result = None
                st.session_state.text_summary_result = None  # Clear any text summaries too
                st.rerun()
        with col2:
            #  Add a download button for convenience
            st.download_button(
                label="⬇️ Download This Markdown",
                data=st.session_state.selected_markdown_content,
                file_name=f"{st.session_state.selected_markdown_name}.md",
                mime="text/markdown"
            )

        st.markdown(f"**Viewing: {st.session_state.selected_markdown_name}**")
        
        # Display the markdown content in a scrollable container
        with st.container():
            st.markdown("### 📄 Document Content")
            st.markdown(st.session_state.selected_markdown_content, unsafe_allow_html=True)
        
        # LLM interaction section
        st.markdown("---")
        st.markdown("## 🤖 LLM Interaction")
        
        # Check if LLM model is selected
        if st.session_state.llm_model == "Select Model":
            st.warning("⚠️ Please select an LLM model from the sidebar to enable summarization and Q&A.")
        else:
            # Create tabs for different LLM functions
            llm_tab1, llm_tab2 = st.tabs(["📝 Document Summarization", "❓ Question & Answer"])
            
            with llm_tab1:
                st.markdown("### 📝 Get an AI Summary of this Document")
                
                if st.button("Summarize Document", key="summarize_btn", type="primary"):
                    # Submit for summarization
                    summary_result = submit_summarization(
                        st.session_state.selected_markdown_content,
                        st.session_state.llm_model
                    )

                # Display summary result if available
                if st.session_state.get("summary_result"):
                    with st.expander("📋 Document Summary", expanded=True):
                        # Use the appropriate key based on the actual response structure
                        summary_text = st.session_state.summary_result.get("summary", 
                                    st.session_state.summary_result.get("content", "No summary available"))
                        st.markdown(summary_text)
                        
                        # Display token usage if available
                        usage = st.session_state.summary_result.get("usage")
                        if usage:
                            try:
                                # Handle usage data which might be a string or dict
                                if isinstance(usage, str):
                                    usage_data = json.loads(usage) if usage.startswith("{") else {"total_tokens": "N/A"}
                                else:
                                    usage_data = usage
                                    
                                st.markdown("**Token Usage:**")
                                cols = st.columns(3)
                                cols[0].metric("Prompt Tokens", usage_data.get("prompt_tokens", "N/A"))
                                cols[1].metric("Completion Tokens", usage_data.get("completion_tokens", "N/A"))
                                cols[2].metric("Total Tokens", usage_data.get("total_tokens", "N/A"))
                            except Exception as e:
                                st.info(f"Token usage data format: {str(e)}")
            
            with llm_tab2:
                st.markdown("### ❓ Ask Questions About the Document")
                user_question = st.text_area("Enter your question about the document:", 
                                            key="question_input", 
                                            placeholder="Ask a question about the document content...")
                
                if st.button("Submit Question", key="question_btn", type="primary"):
                    if not user_question:
                        st.error("Please enter a question.")
                    elif not st.session_state.selected_markdown_content:
                        st.error("No document content available to query.")
                    else:
                        # Submit the question
                        question_result = submit_question(
                            st.session_state.selected_markdown_content,
                            user_question,
                            st.session_state.llm_model
                        )
                
                # Display question result if available
                if st.session_state.get("question_result"):
                    with st.expander("🔍 Answer", expanded=True):
                        st.markdown("**Question:**")
                        question_text = st.session_state.question_result.get("question", user_question)
                        st.markdown(f"*{question_text}*")
                        
                        st.markdown("**Answer:**")
                        answer_text = st.session_state.question_result.get("answer", 
                                    st.session_state.question_result.get("content", "No answer available"))
                        st.markdown(answer_text)
                        
                        # Display token usage if available
                        usage = st.session_state.question_result.get("usage")
                        if usage:
                            try:
                                # Handle usage data which might be a string or dict
                                if isinstance(usage, str):
                                    usage_data = json.loads(usage) if usage.startswith("{") else {"total_tokens": "N/A"}
                                else:
                                    usage_data = usage
                                    
                                st.markdown("**Token Usage:**")
                                cols = st.columns(3)
                                cols[0].metric("Prompt Tokens", usage_data.get("prompt_tokens", "N/A"))
                                cols[1].metric("Completion Tokens", usage_data.get("completion_tokens", "N/A"))
                                cols[2].metric("Total Tokens", usage_data.get("total_tokens", "N/A"))
                            except Exception as e:
                                st.info(f"Token usage data format: {str(e)}")

    elif st.session_state.get("next_clicked", False):
        st.image("images/markdown_viewer.png", use_container_width=True)
        if st.session_state.processing_type == "PDF Extraction":
            # Display tools being used
            if st.session_state.service_type == "Open Source":
                st.subheader("Using Tools: Docling",divider="gray")
            elif st.session_state.service_type == "Enterprise":
                st.subheader("Using Tools: Azure Document Intelligence",divider="gray")
            
            # Display file uploader and buttons
            uploaded_file = st.file_uploader("Upload a PDF File:", type=["pdf"], key="pdf_uploader")
            if uploaded_file:
                st.session_state.file_uploaded = True
                upload_response = upload_pdf(uploaded_file)
                if "error" in upload_response:
                    pass
                else:
                    st.success("✅ PDF File Uploaded Successfully!")

            # if st.session_state.get("extraction_complete", False) and not st.session_state.get("markdown_ready", False):
            if st.button("📑 Convert to Markdown"):
                markdown_response = convert_to_markdown()
                if "error" in markdown_response:
                    st.error(markdown_response["error"])
                else:
                    st.success(markdown_response["message"])
                    st.session_state.markdown_ready = True  # ✅ Set markdown state to True

            # Fetch markdown URLs from the latest job-specific folder
            if st.session_state.get("markdown_ready", False):

                st.markdown("## 📄 Available Markdown Files")
                
                # ✅ Fetch markdown files from API
                markdown_files = fetch_downloadable_markdown()
                
                if not markdown_files or "error" in markdown_files:
                    st.warning("⚠️ No Markdown files found.")
                else:
                    # ✅ Display each markdown file as a selectable option
                    markdown_options = {file["file_name"]: file["download_url"] for file in markdown_files}
                    selected_markdown_name = st.selectbox("Choose a Markdown File", list(markdown_options.keys()), index=0)

                    if selected_markdown_name:
                        selected_markdown_url = markdown_options[selected_markdown_name]

                        # ✅ Add a Download Button for the Selected Markdown
                        st.download_button(
                            label="⬇️ Download Markdown",
                            data=requests.get(selected_markdown_url).text,  # Fetch file content
                            file_name=selected_markdown_name,
                            mime="text/markdown"
                        )

                    if st.button("👀 View Selected Markdown"):
                        if not selected_markdown_name:
                            st.warning("⚠️ Please select a Markdown file.")
                        else:
                            # ✅ Fetch actual markdown content
                            markdown_content = requests.get(selected_markdown_url).text

                            # ✅ Store selected markdown in session state
                            st.session_state.selected_markdown_content = markdown_content

                # ✅ Show Markdown Content if a file is selected
                if st.session_state.get("selected_markdown_content", None):
                    st.markdown("### 📄 Markdown Viewer")
                    
                    # ✅ Use `st.markdown()` to properly render Markdown with headings, lists, etc.
                    st.markdown(st.session_state.selected_markdown_content, unsafe_allow_html=True)


