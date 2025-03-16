import os
import base64
import re
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
import litellm
from dotenv import load_dotenv

# Load environment variables and configure debug logging
load_dotenv()
os.environ["LITELLM_LOG"] = "DEBUG"  # Replace deprecated set_verbose

# Configure LiteLLM with API keys
litellm.gemini_key = os.getenv("GEMINI_API_KEY")
os.environ["ANTHROPIC_API_KEY"] = os.getenv("CLAUDE_API_KEY")
litellm.anthropic_api_key = os.getenv("CLAUDE_API_KEY")
os.environ["DEEPSEEK_API_KEY"] = os.getenv("DEEP_SEEK_API_KEY")
litellm.deepseek_api_key = os.getenv("DEEP_SEEK_API_KEY")

# Debug output to check API keys
print(f"API Keys Status:")
print(f"- Gemini:    {'✓' if litellm.gemini_key else '✗'}")
print(f"- Anthropic: {'✓' if os.getenv('ANTHROPIC_API_KEY') else '✗'}")
print(f"- DeepSeek:  {'✓' if litellm.deepseek_api_key else '✗'}")
print("DEEPSEEK_Key is", os.getenv('DEEP_SEEK_API_KEY'))
print("Anthropic_Key is", os.getenv('ANTHROPIC_API_KEY'))

# Model configurations
MODEL_CONFIGS = {
    "gpt4o": {
        "name": "GPT-4o",
        "model": "openai/gpt-4o",
        "max_input_tokens": 128000,
        "max_output_tokens": 4096,
        "supports_images": True,
    },
    "gemini": {
        "name": "Gemini Flash",
        "model": "gemini/gemini-1.5-flash",
        "max_input_tokens": 100000,
        "max_output_tokens": 4000,
        "supports_images": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "model": "deepseek/deepseek-reasoner", 
        "max_input_tokens": 16000,
        "max_output_tokens": 2048,
        "supports_images": False,
    },
    "claude": {
        "name": "Claude 3 Sonnet",
        "model": "claude/claude-3-5-sonnet-20240620",  # Updated with provider prefix
        "max_input_tokens": 100000,
        "max_output_tokens": 4096, 
        "supports_images": True,
    },
    "grok": {
        "name": "Grok",
        "model": "xai/grok-1", 
        "max_input_tokens": 8192,
        "max_output_tokens": 2048,
        "supports_images": True,
    }
}

def encode_image_to_base64(image_path: str) -> str:
    """Convert an image file to base64 encoding."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def read_markdown_file(markdown_path: str) -> str:
    """Read and return the contents of a markdown file."""
    try:
        with open(markdown_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading markdown file {markdown_path}: {e}")
        return f"[Error reading file: {markdown_path}]"

def extract_image_paths_from_markdown(markdown_content: str, base_dir: str) -> List[str]:
    """
    Extract image paths from markdown content.
    
    Args:
        markdown_content: The markdown content with image references
        base_dir: The base directory where images should be found relative to
        
    Returns:
        List of full paths to image files
    """
    # Match markdown image syntax: ![alt text](image_path)
    image_matches = re.findall(r'!\[.*?\]\((.*?)\)', markdown_content)
    
    # Match HTML img tags: <img src="image_path" />
    html_matches = re.findall(r'<img[^>]*src=["\'](.*?)["\'][^>]*>', markdown_content)
    
    # Combine all matches
    all_matches = image_matches + html_matches
    
    # Convert relative paths to absolute paths
    image_paths = []
    for img_path in all_matches:
        # Handle both local and URL images
        if img_path.startswith(('http://', 'https://', 'data:')):
            # Skip external URLs and data URIs
            continue
        
        # Convert relative path to absolute
        abs_path = os.path.abspath(os.path.join(base_dir, img_path))
        if os.path.exists(abs_path):
            image_paths.append(abs_path)
        else:
            print(f"Warning: Image file not found: {abs_path}")
    
    return image_paths

def process_markdown_with_images(markdown_path: str) -> Dict[str, Any]:
    """
    Process a markdown file and extract its content and image paths.
    
    Args:
        markdown_path: Path to the markdown file
        
    Returns:
        Dictionary with text content and image paths
    """
    # Get the directory containing the markdown file
    base_dir = os.path.dirname(os.path.abspath(markdown_path))
    
    # Read the markdown content
    markdown_content = read_markdown_file(markdown_path)
    
    # Extract image paths
    image_paths = extract_image_paths_from_markdown(markdown_content, base_dir)
    
    return {
        "text_content": markdown_content,
        "image_paths": image_paths
    }

def create_llm_response_from_markdown(
    markdown_path: str, 
    model_id: str = "claude-3-5-sonnet-20241022",
    task_type: Literal["summary", "qa"] = "summary",
    question: Optional[str] = None,
    max_images: int = 5
) -> Dict[str, Any]:  # Changed return type to Dict to include token usage
    """
    Generate a response from markdown content using the specified model.
    
    Args:
        markdown_path: Path to the markdown file
        model_id: ID of the model to use (from MODEL_CONFIGS)
        task_type: Type of task - "summary" or "qa"
        question: Question for Q&A mode (required if task_type is "qa")
        max_images: Maximum number of images to include
        
    Returns:
        A dictionary containing the response and token usage information
    """
    try:
        # Validate inputs
        if task_type == "qa" and not question:
            return {"content": "Error: Question must be provided for Q&A task type.", "usage": {"total_tokens": 0}}
            
        if model_id not in MODEL_CONFIGS:
            return {"content": f"Error: Unsupported model '{model_id}'. Choose from: {', '.join(MODEL_CONFIGS.keys())}", "usage": {"total_tokens": 0}}
        
        model_config = MODEL_CONFIGS[model_id]
        
        # Check API key availability for the selected model before proceeding
        model_config = MODEL_CONFIGS[model_id]
        model_name = model_config["model"]
        api_key_status = False
        
        if model_id == "gemini" and litellm.gemini_key:
            api_key_status = True
        elif model_id == "openai" and litellm.openai_api_key:
            api_key_status = True
        elif model_id == "claude" and litellm.anthropic_api_key: 
            api_key_status = True
        elif model_id == "deepseek" and litellm.deepseek_api_key:
            api_key_status = True
        elif model_id == "xai" and litellm.xai_api_key:
            api_key_status = True
            
        if not api_key_status:
            return {"content": f"Error: API key not found for {model_id}. Please check your .env file.", "usage": {"total_tokens": 0}}
        
        # Check if file exists
        if not os.path.exists(markdown_path):
            return {"content": f"Error: Markdown file not found at {markdown_path}", "usage": {"total_tokens": 0}}
            
        # Process the markdown file
        content = process_markdown_with_images(markdown_path)
        
        # Prepare the prompt based on task type
        if task_type == "summary":
            prompt_text = f"""
            I need you to create a comprehensive summary of the following document content.
            
            The content is from a Markdown file that includes text and may reference images.
            Please analyze all the provided information and create a well-structured summary that:
            
            1. Identifies the main topic and purpose of the document
            2. Summarizes the key points and findings
            3. Highlights important data from any tables
            4. Describes what's shown in the images
            5. Organizes the information in a logical flow
            
            Here's the markdown content:
            
            {content["text_content"]}
            """
        else:  # Q&A mode
            prompt_text = f"""
            Based on the following document content, please answer this question:
            
            {question}
            
            The document content is from a Markdown file that includes text and may reference images.
            Please analyze all provided information carefully before giving your answer.
            
            Here's the markdown content:
            
            {content["text_content"]}
            """
        
        # Prepare the messages with text and images
        messages = [{"role": "user", "content": prompt_text}]
        
        # Add images if model supports images
        if model_config["supports_images"]:
            # Add images if available (limited to max_images)
            image_paths = content["image_paths"][:max_images]  # Limit number of images
            
            if image_paths:
                # For multimodal input with images
                image_parts = []
                for img_path in image_paths:
                    try:
                        base64_image = encode_image_to_base64(img_path)
                        image_parts.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        })
                    except Exception as e:
                        print(f"Error encoding image {img_path}: {e}")
                
                # Add image parts to the message
                if image_parts:
                    messages = [
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": prompt_text},
                                *image_parts
                            ]
                        }
                    ]
        
        # Call model using LiteLLM with specific configurations per model
        if model_id == "claude":
            response = litellm.completion(
                model="anthropic/claude-3-5-sonnet-20240620",  # Updated with provider prefix
                messages=messages,
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"],
                api_key=os.getenv("CLAUDE_API_KEY")
            )
        elif model_id == "gemini":
            response = litellm.completion(
                model="gemini-1.5-flash",  # Direct model name
                messages=messages,
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"]
            )
        elif model_id == "deepseek":
            response = litellm.completion(
                model="deepseek/deepseek-reasoner",  # Updated with provider prefix
                messages=messages,
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"]  # Explicitly pass API key
            )
        else:
            response = litellm.completion(
                model=model_config["model"],
                messages=messages,
                temperature=0.3,
                max_tokens=model_config["max_output_tokens"]
            )
        
        # Extract and return the response with token usage
        if response and response.choices and response.choices[0].message.content:
            # Extract token usage information
            usage_info = {
                "prompt_tokens": response.usage.prompt_tokens if hasattr(response, 'usage') and hasattr(response.usage, 'prompt_tokens') else 0,
                "completion_tokens": response.usage.completion_tokens if hasattr(response, 'usage') and hasattr(response.usage, 'completion_tokens') else 0,
                "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') and hasattr(response.usage, 'total_tokens') else 0
            }
            
            return {
                "content": response.choices[0].message.content,
                "usage": usage_info
            }
        else:
            return {
                "content": f"Error: No response generated from {model_config['name']}.",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            }
    
    except Exception as e:
        return {
            "content": f"Error generating response: {str(e)}",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
    
def summarize_markdown(
    markdown_path: str, 
    model_id: str = "gemini",
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a summary for a markdown file.
    
    Args:
        markdown_path: Path to the markdown file
        model_id: Model ID to use for summarization
        output_dir: Optional directory to save the summary
        
    Returns:
        Dictionary with the generated summary and token usage information
    """
    print(f"Generating summary for markdown file: {markdown_path} using {MODEL_CONFIGS[model_id]['name']}")
    
    # Verify that markdown_path exists and is a file
    if not os.path.isfile(markdown_path):
        error_msg = f"File not found: {markdown_path}"
        print(error_msg)
        return {"summary": f"Error: {error_msg}", "usage": {"total_tokens": 0}}
    
    # Set up the output directory
    if not output_dir:
        output_dir = os.path.dirname(os.path.abspath(markdown_path))
    
    # Ensure output_dir is an absolute path and valid
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)
    
    try:
        # Create the output directory safely
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate the summary
        response = create_llm_response_from_markdown(markdown_path, model_id, task_type="summary")
        
        summary = response["content"]
        usage = response["usage"]
        
        # Get the original filename without extension
        markdown_filename = Path(markdown_path).stem
        
        # Save the summary to a file
        summary_path = os.path.join(output_dir, f"{markdown_filename}_{model_id}_summary.md")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary)
        
        print(f"Summary saved to: {summary_path}")
        return {"summary": summary, "usage": usage}
    
    except Exception as e:
        error_msg = f"Error generating summary: {str(e)}"
        print(error_msg)
        return {"summary": f"Error: {error_msg}", "usage": {"total_tokens": 0}}

def qa_markdown(
    markdown_path: str, 
    question: str,
    model_id: str = "gemini",
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Answer a question based on markdown content using the specified model.
    
    Args:
        markdown_path: Path to the markdown file
        question: Question to answer
        model_id: ID of the model to use
        output_dir: Optional directory to save the answer
        
    Returns:
        Dictionary with the generated answer and token usage information
    """
    print(f"Answering question for markdown file: {markdown_path} using {MODEL_CONFIGS[model_id]['name']}")
    print(f"Question: {question}")
    
    if not output_dir:
        # Use the same directory as the markdown file
        output_dir = os.path.dirname(os.path.abspath(markdown_path))
    
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate the answer
    response = create_llm_response_from_markdown(
        markdown_path, 
        model_id, 
        task_type="qa", 
        question=question
    )
    
    answer = response["content"]
    usage = response["usage"]
    
    # Get the original filename without extension and sanitize question for filename
    markdown_filename = Path(markdown_path).stem
    question_part = re.sub(r'[^\w\s-]', '', question)[:30].strip().replace(' ', '_')
    
    # Save the answer to a file
    answer_path = os.path.join(output_dir, f"{markdown_filename}_{model_id}_qa_{question_part}.md")
    with open(answer_path, "w", encoding="utf-8") as f:
        f.write(f"# Question\n\n{question}\n\n# Answer\n\n{answer}")
    
    print(f"Answer saved to: {answer_path}")
    return {"answer": answer, "question": question, "usage": usage}

if __name__ == "__main__":
    # Example usage:
    # Replace with the path to your markdown file
    markdown_file = "Cloud_Run.md"
    
    if os.path.exists(markdown_file):
        # Example of using different models for summary
        for model in ["gemini","deepseek","claude","grok","gpt4o"]:
            try:
                summary = summarize_markdown(markdown_file, model_id=model)
                print(f"\n{MODEL_CONFIGS[model]['name']} Summary Preview:")
                print(summary[:500] + "..." if len(summary) > 500 else summary)
            except Exception as e:
                print(f"Error with {model}: {str(e)}")
        
        # Example of Q&A
        question = "What are the risks mentioned in the Q4 report?"
        answer = qa_markdown(markdown_file, question, model_id="gemini")
        print("\nQ&A Preview:")
        print(answer[:500] + "..." if len(answer) > 500 else answer)
    else:
        print(f"Markdown file not found: {markdown_file}")