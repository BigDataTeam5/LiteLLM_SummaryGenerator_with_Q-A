import os
import base64
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
import litellm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure LiteLLM with Claude API key
litellm.api_key = os.getenv("ANTHROPIC_API_KEY")

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

def create_claude_summary_from_markdown(markdown_path: str, max_images: int = 5) -> str:
    """
    Generate a summary of markdown content using Claude.
    """
    try:
        if not os.path.exists(markdown_path):
            return f"Error: Markdown file not found at {markdown_path}"
            
        content = process_markdown_with_images(markdown_path)
        
        # Prepare the prompt
        prompt_text = f"""
        Please create a comprehensive summary of the following document content.
        
        The content is from a Markdown file that includes text and may reference images.
        Please analyze all the provided information and create a well-structured summary that:
        
        1. Identifies the main topic and purpose of the document
        2. Summarizes the key points and findings
        3. Highlights important data from any tables
        4. Describes what's shown in the images
        5. Organizes the information in a logical flow
        
        Document content:
        {content["text_content"]}
        """
        
        # Prepare media content for Claude
        media_content = []
        for img_path in content["image_paths"][:max_images]:
            try:
                base64_image = encode_image_to_base64(img_path)
                media_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image
                    }
                })
            except Exception as e:
                print(f"Error encoding image {img_path}: {e}")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    *media_content
                ]
            }
        ]
        
        response = litellm.completion(
            model="claude-3-opus-20240229",  # Using Claude 3
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )
        
        if response and response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            return "Error: No response generated from Claude."
    
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
    summary = create_claude_summary_from_markdown(markdown_path)
    
    # Get the original filename without extension
    markdown_filename = Path(markdown_path).stem
    
    # Save the summary to a file
    summary_path = os.path.join(output_dir, f"{markdown_filename}_claude_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(f"Summary saved to: {summary_path}")
    return summary

def is_safe_prompt(prompt: str) -> bool:
    """
    Check if a prompt is safe to process.
    Returns True if safe, False if potentially dangerous.
    """
    # Lowercase for consistent checking
    prompt_lower = prompt.lower()
    
    # Dangerous patterns to check for
    dangerous_patterns = [
        # System/Security
        r'system\(.*\)',
        r'exec\(.*\)',
        r'eval\(.*\)',
        r'sudo',
        r'rm -rf',
        # Harmful Content
        r'hack',
        r'exploit',
        r'vulnerability',
        r'malware',
        r'virus',
        # Personal/Sensitive Data
        r'password',
        r'credit card',
        r'ssn',
        r'social security',
        # Inappropriate Content
        r'porn',
        r'nsfw',
        r'explicit',
        # Harmful Behaviors
        r'suicide',
        r'self-harm',
        r'kill',
        r'weapon',
        # Discrimination
        r'racist',
        r'nazi',
        r'hate speech'
    ]
    
    # Check for dangerous patterns
    for pattern in dangerous_patterns:
        if re.search(pattern, prompt_lower):
            return False
    
    return True

def validate_and_sanitize_prompt(prompt: str) -> tuple[bool, str]:
    """
    Validate and sanitize a user prompt.
    Returns (is_safe, message) tuple.
    """
    # Check for empty or whitespace
    if not prompt or prompt.isspace():
        return False, "Prompt cannot be empty."
    
    # Check length limits
    if len(prompt) > 1000:
        return False, "Prompt is too long. Please limit to 1000 characters."
    
    # Check for safe content
    if not is_safe_prompt(prompt):
        return False, "I apologize, but I cannot process this prompt as it may contain inappropriate or dangerous content."
    
    # Sanitize the prompt
    sanitized = re.sub(r'[<>]', '', prompt)  # Remove potential HTML/XML tags
    sanitized = ' '.join(sanitized.split())   # Normalize whitespace
    
    return True, sanitized

def answer_question_about_markdown(markdown_path: str, question: str, max_images: int = 5) -> str:
    """
    Generate an answer to a specific question about the markdown content using Claude.
    """
    # Validate the question first
    is_safe, result = validate_and_sanitize_prompt(question)
    if not is_safe:
        return result
        
    question = result  # Use sanitized question
    
    try:
        if not os.path.exists(markdown_path):
            return f"Error: Markdown file not found at {markdown_path}"
            
        content = process_markdown_with_images(markdown_path)
        
        prompt_text = f"""
        Please answer the following question about the document content.
        Use only the information provided in the document to answer.
        If the answer cannot be found in the document, please say so.
        Avoid generating any harmful, inappropriate, or dangerous content.
        If the question asks for harmful content, decline to answer.

        Document content:
        {content["text_content"]}

        Question: {question}
        """
        
        # Prepare media content for Claude
        media_content = []
        for img_path in content["image_paths"][:max_images]:
            try:
                base64_image = encode_image_to_base64(img_path)
                media_content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64_image
                    }
                })
            except Exception as e:
                print(f"Error encoding image {img_path}: {e}")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    *media_content
                ]
            }
        ]
        
        response = litellm.completion(
            model="claude-3-5-sonnet-20241022",
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )
        
        if response and response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            return "Error: No response generated from Claude."
    
    except Exception as e:
        return f"Error generating answer: {str(e)}"

if __name__ == "__main__":
    markdown_file = "2408.09869v5-with-image-refs.md"
    
    if not os.path.exists(markdown_file):
        print(f"Markdown file not found: {markdown_file}")
        exit(1)

    while True:
        print("\nEnter your question about the document (or 'quit' to exit):")
        question = input("> ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            break
        
        # Validate the question
        is_safe, result = validate_and_sanitize_prompt(question)
        if not is_safe:
            print("\nWarning:", result)
            continue
            
        answer = answer_question_about_markdown(markdown_file, result)
        print("\nAnswer:")
        print(answer)