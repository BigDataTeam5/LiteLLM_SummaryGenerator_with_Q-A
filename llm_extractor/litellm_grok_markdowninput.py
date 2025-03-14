import os
import base64
import re
import requests
from typing import List, Dict, Any, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Grok API Key
GROK_API_KEY = os.getenv("GROK_API_KEY")
GROK_API_URL = "https://api.x.ai/grok/completions"  # Replace with the correct endpoint

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
    """
    image_matches = re.findall(r'!\[.*?\]\((.*?)\)', markdown_content)
    html_matches = re.findall(r'<img[^>]*src=["\'](.*?)["\'][^>]*>', markdown_content)
    
    all_matches = image_matches + html_matches
    
    image_paths = []
    for img_path in all_matches:
        if img_path.startswith(('http://', 'https://', 'data:')):
            continue
        
        abs_path = os.path.abspath(os.path.join(base_dir, img_path))
        if os.path.exists(abs_path):
            image_paths.append(abs_path)
        else:
            print(f"Warning: Image file not found: {abs_path}")
    
    return image_paths

def process_markdown_with_images(markdown_path: str) -> Dict[str, Any]:
    """
    Process a markdown file and extract its content and image paths.
    """
    base_dir = os.path.dirname(os.path.abspath(markdown_path))
    markdown_content = read_markdown_file(markdown_path)
    image_paths = extract_image_paths_from_markdown(markdown_content, base_dir)
    
    return {
        "text_content": markdown_content,
        "image_paths": image_paths
    }

def create_grok_summary_from_markdown(markdown_path: str, max_images: int = 5) -> str:
    """
    Generate a summary of markdown content using Grok (xAI).
    """
    try:
        if not os.path.exists(markdown_path):
            return f"Error: Markdown file not found at {markdown_path}"
        
        content = process_markdown_with_images(markdown_path)
        
        prompt_text = f"""
        I need you to create a structured summary of the following Markdown document.
        
        **Requirements:**
        1. Identify the main topic and purpose.
        2. Summarize key points and findings.
        3. Highlight key data from tables.
        4. Describe the images if provided.
        5. Organize in a structured format.
        
        **Markdown Content:**
        
        {content["text_content"]}
        """
        
        payload = {
            "model": "grok-1",  # Update if xAI has a different model version
            "prompt": prompt_text,
            "temperature": 0.3,
            "max_tokens": 4000
        }

        headers = {
            "Authorization": f"Bearer {GROK_API_KEY}",
            "Content-Type": "application/json"
        }

        response = requests.post(GROK_API_URL, json=payload, headers=headers)

        if response.status_code == 200:
            response_json = response.json()
            return response_json.get("text", "Error: No response from Grok.")
        else:
            return f"Error: Grok API returned status {response.status_code} - {response.text}"

    except Exception as e:
        return f"Error generating summary: {str(e)}"

def summarize_markdown(markdown_path: str, output_dir: Optional[str] = None) -> str:
    """
    Summarize a markdown file using Grok (xAI).
    """
    print(f"Generating summary for markdown file: {markdown_path}")
    
    if not output_dir:
        output_dir = os.path.dirname(os.path.abspath(markdown_path))
    
    os.makedirs(output_dir, exist_ok=True)
    
    summary = create_grok_summary_from_markdown(markdown_path)
    
    markdown_filename = Path(markdown_path).stem
    summary_path = os.path.join(output_dir, f"{markdown_filename}_grok_summary.md")
    
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(f"Summary saved to: {summary_path}")
    return summary

if __name__ == "__main__":
    markdown_file = "example.md"  # Change this to your markdown file
    
    if os.path.exists(markdown_file):
        summary = summarize_markdown(markdown_file)
        print("\nSummary Preview:")
        print(summary[:500] + "..." if len(summary) > 500 else summary)
    else:
        print(f"Markdown file not found: {markdown_file}")
