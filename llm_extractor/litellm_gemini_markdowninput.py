import os
import base64
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import litellm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure LiteLLM with your Gemini API key
litellm.api_key = os.getenv("gemini_api_key")

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

def create_gemini_summary_from_markdown(markdown_path: str, max_images: int = 5) -> str:
    """
    Generate a summary of markdown content using Gemini.
    
    Args:
        markdown_path: Path to the markdown file
        max_images: Maximum number of images to include (Gemini has input limits)
        
    Returns:
        A string containing the summary
    """
    try:
        # Check if file exists
        if not os.path.exists(markdown_path):
            return f"Error: Markdown file not found at {markdown_path}"
            
        # Process the markdown file
        content = process_markdown_with_images(markdown_path)
        
        # Prepare the prompt
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
        
        # Prepare the messages with text and images
        messages = [{"role": "user", "content": prompt_text}]
        
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
        
        # Call Gemini model using LiteLLM - use the newer 1.5 models
        # Use gemini-1.5-flash for both text and image inputs
        response = litellm.completion(
            model="gemini/gemini-1.5-flash",  # Using the newer model
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )
        
        # Extract and return the summary
        if response and response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            return "Error: No response generated from Gemini."
    
    except Exception as e:
        return f"Error generating summary: {str(e)}"

def summarize_markdown(markdown_path: str, output_dir: Optional[str] = None) -> str:
    """
    Main function to summarize markdown content.
    
    Args:
        markdown_path: Path to the markdown file
        output_dir: Optional directory to save the summary (defaults to same directory as markdown)
        
    Returns:
        The generated summary
    """
    print(f"Generating summary for markdown file: {markdown_path}")
    
    if not output_dir:
        # Use the same directory as the markdown file
        output_dir = os.path.dirname(os.path.abspath(markdown_path))
    
    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate the summary
    summary = create_gemini_summary_from_markdown(markdown_path)
    
    # Get the original filename without extension
    markdown_filename = Path(markdown_path).stem
    
    # Save the summary to a file
    summary_path = os.path.join(output_dir, f"{markdown_filename}_gemini_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(f"Summary saved to: {summary_path}")
    return summary

if __name__ == "__main__":
    # Example usage:
    # Replace with the path to your markdown file
    markdown_file = "../2408.09869v5-with-image-refs.md"
    
    if os.path.exists(markdown_file):
        summary = summarize_markdown(markdown_file)
        print("\nSummary Preview:")
        print(summary[:500] + "..." if len(summary) > 500 else summary)
    else:
        print(f"Markdown file not found: {markdown_file}")