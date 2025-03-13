import streamlit as st
import requests
import time
import sys
import os
sys.path.append("LLM_Interactor")
# from logger import api_logger

# Streamlit UI
st.set_page_config(page_title="", layout="wide")
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

# FastAPI Base URL (Update this with the correct deployed FastAPI URL)
# FASTAPI_URL = "https://fastapi-app-974490277552.us-central1.run.app"
FASTAPI_URL = "http://localhost:8080"
# API Endpoints
UPLOAD_PDF_API = f"{FASTAPI_URL}/upload-pdf"
LATEST_FILE_API = f"{FASTAPI_URL}/get-latest-file-url"
PARSE_PDF_API = f"{FASTAPI_URL}/parse-pdf"
PARSE_PDF_AZURE_API = f"{FASTAPI_URL}/parse-pdf-azure"
CONVERT_MARKDOWN_API = f"{FASTAPI_URL}/convert-pdf-markdown"
FETCH_MARKDOWN_API = f"{FASTAPI_URL}/fetch-latest-markdown-urls"
FETCH_DOWNLOADABLE_MARKDOWN_API = f"{FASTAPI_URL}/fetch-latest-markdown-downloads"
FETCH_MARKDOWN_HISTORY = f"{FASTAPI_URL}/list-image-ref-markdowns"
SUMMARIZE_API = f"{FASTAPI_URL}/summarize"
ASK_QUESTION_API = f"{FASTAPI_URL}/ask-question"
GET_LLM_RESULT_API = f"{FASTAPI_URL}/get-llm-result"
uploaded_file = None  # Define uploaded_file globally


# Function to Upload File to S3
def upload_pdf(file):
    try:
        files = {"file": (file.name, file.getvalue(), "application/pdf")}
        with st.spinner("📤 Uploading PDF... Please wait."):
            service_type = st.session_state.get("service_type", None)
            response = requests.post(UPLOAD_PDF_API, files=files, params={"service_type": service_type})

        if response.status_code == 200:
            st.session_state.file_uploaded = True
            return response.json()
        else:
            try:
                error_detail = response.json().get("detail", f"Upload failed: {response.status_code}")
            except ValueError:
                error_detail = f"Upload failed: {response.status_code}"
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
            response_latest = requests.get(LATEST_FILE_API,params={"service_type": service_type})
            if response_latest.status_code != 200:
                progress_bar.empty()
                return {"error": f"❌ Failed to fetch latest file URL: {response_latest.text}"}

            # Step 2: Convert PDF to Markdown
            response = requests.get(CONVERT_MARKDOWN_API)
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

            response = requests.get(FETCH_MARKDOWN_API)
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
            response = requests.get(FETCH_DOWNLOADABLE_MARKDOWN_API)
        
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
            response = requests.get(FETCH_MARKDOWN_HISTORY)
        
        if response.status_code == 200:
            markdown_data = response.json()
            # Process the markdown files for display in sidebar history
            history_items = []
            
            for item in markdown_data.get("image_ref_markdowns", []):
                display_name = item["file_name"].replace("-with-image-refs", "").replace(".md", "")
                history_items.append({
                    "label": display_name,
                    "url": item["download_url"],
                    "folder": item["folder"],
                    "last_modified": item["last_modified"]
                })
            
            # Update session state with the history items
            st.session_state.markdown_history = history_items
            return history_items
        else:
            st.error(f"Failed to fetch markdown history! Response: {response.text}")
            return []

    except requests.RequestException as e:
        st.error(f"Request error: {str(e)}")
        return []
    
if not st.session_state.markdown_history:
    fetch_markdown_history()

# Function to submit summarization request
def submit_summarization(content, model):
    """Submit content to be summarized by the selected LLM model"""
    try:
        with st.spinner("⏳ Generating summary with LLM... This may take a moment."):
            # Generate a unique request ID
            request_id = f"summary_{int(time.time())}"
            
            # Submit the summarization request
            response = requests.post(
                SUMMARIZE_API,
                json={
                    "request_id": request_id,
                    "content": content,
                    "model": model
                }
            )
            
            if response.status_code == 202:
                st.session_state.processing_summary = True
                
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

# Function to submit question to LLM
def submit_question(content, question, model):
    """Submit content and question to be answered by the selected LLM model"""
    try:
        with st.spinner("⏳ Processing your question with LLM... This may take a moment."):
            # Generate a unique request ID
            request_id = f"question_{int(time.time())}"
            
            # Submit the question request
            response = requests.post(
                ASK_QUESTION_API,
                json={
                    "request_id": request_id,
                    "content": content,
                    "question": question,
                    "model": model
                }
            )
            
            if response.status_code == 202:
                st.session_state.processing_question = True
                
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

# Function to poll for LLM results
def poll_for_llm_result(request_id, max_retries=30, interval=2):
    """Poll the API for LLM processing results"""
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(f"{GET_LLM_RESULT_API}/{request_id}")
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "completed":
                    return result
                elif result.get("status") == "error":
                    return {"error": result.get("error", "Unknown error occurred")}
            
            # If not ready yet, wait and retry
            time.sleep(interval)
            retries += 1
            
            # Update progress
            if retries % 5 == 0:
                st.info(f"Still waiting for results... ({retries}/{max_retries})")
                
        except Exception as e:
            return {"error": f"Error polling for results: {str(e)}"}
    
    return {"error": "Timed out waiting for LLM response"}

# Sidebar UI
with st.sidebar:
    st.subheader("Select Options")

    # Dropdown for processing type
    processing_type = st.selectbox("Processing Type:", ["Select an option", "PDF Extraction"], index=0)
    st.session_state.processing_type = processing_type

    # Dropdown for service type
    service_type = st.selectbox("Service Type:", ["Select Service", "Open Source", "Enterprise"], index=0)
    st.session_state.service_type = service_type

    #Dropdown for selecting llm model using Litellm
    llm_model = st.selectbox("Select LLM Model:", ["Select Model", "chatgpt", "claude","grok","gemini","deepseek"], index=0)
    st.session_state.llm_model = llm_model

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
# Show Markdown Content from history if it exists (outside other conditionals)
if st.session_state.get("selected_markdown_content", None):
    st.image("../images/summary_generator.png", use_container_width=True)
    col1,col2 =  st.columns([1,0.3])
    with col1:
         if st.button("Back to Main Menu"):
            st.session_state.selected_markdown_content = None
            st.session_state.selected_markdown_name = None
            st.session_state.markdown_ready = False
            st.session_state.next_clicked = False
            st.session_state.summary_result = None
            st.session_state.question_result = None
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
    
    # LLM summarization and Q&A section
    st.markdown("---")
    st.markdown("## 🤖 LLM Interaction")
    
    # Check if LLM model is selected
    if st.session_state.llm_model == "Select Model":
        st.warning("⚠️ Please select an LLM model from the sidebar to enable summarization and Q&A.")
    else:
        # Summarization section
        st.markdown("### 📝 Document Summarization")
        
        if st.button("Summarize Document", key="summarize_btn"):
            if not st.session_state.selected_markdown_content:
                st.error("No document content available to summarize.")
            else:
                # Submit for summarization
                summary_result = submit_summarization(
                    st.session_state.selected_markdown_content,
                    st.session_state.llm_model
                )

        # Display summary result if available
        if st.session_state.summary_result:
            with st.expander("📋 Document Summary", expanded=True):
                st.markdown(st.session_state.summary_result.get("content", "No summary available"))
                
                # Display token usage if available
                usage = st.session_state.summary_result.get("usage")
                if usage:
                    try:
                        usage_data = eval(usage)
                        st.markdown("**Token Usage:**")
                        cols = st.columns(3)
                        cols[0].metric("Prompt Tokens", usage_data.get("prompt_tokens", 0))
                        cols[1].metric("Completion Tokens", usage_data.get("completion_tokens", 0))
                        cols[2].metric("Total Tokens", usage_data.get("total_tokens", 0))
                    except:
                        st.info("Token usage data not available")
        
        # Question answering section
        st.markdown("### ❓ Ask Questions About the Document")
        user_question = st.text_area("Enter your question about the document:", key="question_input")
        
        if st.button("Submit Question", key="question_btn"):
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
        if st.session_state.question_result:
            with st.expander("🔍 Answer", expanded=True):
                st.markdown("**Question:**")
                st.markdown(st.session_state.question_result.get("question", "No question available"))
                
                st.markdown("**Answer:**")
                st.markdown(st.session_state.question_result.get("content", "No answer available"))
                
                # Display token usage if available
                usage = st.session_state.question_result.get("usage")
                if usage:
                    try:
                        usage_data = eval(usage)
                        st.markdown("**Token Usage:**")
                        cols = st.columns(3)
                        cols[0].metric("Prompt Tokens", usage_data.get("prompt_tokens", 0))
                        cols[1].metric("Completion Tokens", usage_data.get("completion_tokens", 0))
                        cols[2].metric("Total Tokens", usage_data.get("total_tokens", 0))
                    except:
                        st.info("Token usage data not available")

elif st.session_state.get("next_clicked", False):
    st.image("../images/markdown_viewer.png", use_container_width=True)
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


