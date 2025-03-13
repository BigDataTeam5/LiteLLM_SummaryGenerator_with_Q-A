import os
import sys
import time
import json
import redis
import asyncio
import litellm
from dotenv import load_dotenv

# Rest of your file remains the same...

# Add the root directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from api.logger import api_logger, log_error

# Load environment variables
load_dotenv()

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    db=REDIS_DB,
    decode_responses=True
)

# Stream names
SUMMARY_STREAM = "summary_requests"
QUESTION_STREAM = "question_requests"
RESULT_STREAM = "llm_results"

# Model mapping for LiteLLM
model_mapping = {
    "chatgpt": "gpt-4o", 
    "claude": "anthropic.claude-3-opus-20240229",
    "grok": "xai.grok-1",
    "gemini": "gemini/gemini-1.5-flash",
    "deepseek": "deepseek-ai/deepseek-chat"
}

# API key mapping - load these from environment variables
api_keys = {
    "gpt-4o": os.getenv("OPENAI_API_KEY"),
    "anthropic.claude-3-opus-20240229": os.getenv("ANTHROPIC_API_KEY"),
    "xai.grok-1": os.getenv("GROK_API_KEY"),
    "gemini/gemini-1.5-flash": os.getenv("GEMINI_API_KEY"),
    "deepseek-ai/deepseek-chat": os.getenv("DEEPSEEK_API_KEY")
}

def get_api_key_for_model(model):
    """Get the appropriate API key for the model"""
    actual_model = model_mapping.get(model, model)
    return api_keys.get(actual_model)

async def process_summary_request(data):
    """Process a summary request from the Redis stream"""
    request_id = data.get("request_id")
    content = data.get("content")
    model_name = data.get("model")
    
    api_logger.info(f"Processing summary request {request_id} with model {model_name}")
    
    try:
        # Map the friendly model name to the actual model identifier
        model = model_mapping.get(model_name, model_name)
        
        # Set the API key for the model
        litellm.api_key = get_api_key_for_model(model_name)
        
        # Prepare messages for LiteLLM
        messages = [
            {"role": "system", "content": "You are a helpful assistant that creates concise, informative summaries."},
            {"role": "user", "content": f"Please summarize the following content:\n\n{content}"}
        ]
        
        # Call the LLM through LiteLLM
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )
        
        # Extract the result
        summary = response.choices[0].message.content
        usage = response.usage
        
        # Format the result for Redis
        result = {
            "request_id": request_id,
            "content": summary,
            "usage": json.dumps(usage),
            "model": model,
            "timestamp": str(time.time())
        }
        
        # Publish to result stream
        redis_client.xadd(RESULT_STREAM, result)
        api_logger.info(f"Published summary result for request {request_id}")
        
        return True
    
    except Exception as e:
        log_error(f"Error processing summary request {request_id}", e)
        
        # Publish error result
        error_result = {
            "request_id": request_id,
            "error": str(e),
            "timestamp": str(time.time())
        }
        redis_client.xadd(RESULT_STREAM, error_result)
        return False

async def process_question_request(data):
    """Process a question request from the Redis stream"""
    request_id = data.get("request_id")
    content = data.get("content")
    question = data.get("question")
    model_name = data.get("model")
    
    api_logger.info(f"Processing question request {request_id} with model {model_name}")
    
    try:
        # Map the friendly model name to the actual model identifier
        model = model_mapping.get(model_name, model_name)
        
        # Set the API key for the model
        litellm.api_key = get_api_key_for_model(model_name)
        
        # Prepare messages for LiteLLM
        messages = [
            {"role": "system", "content": "You are a helpful assistant that accurately answers questions based on the provided content."},
            {"role": "user", "content": f"Based on the following content:\n\n{content}\n\nPlease answer this question: {question}"}
        ]
        
        # Call the LLM through LiteLLM
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=1000
        )
        
        # Extract the result
        answer = response.choices[0].message.content
        usage = response.usage
        
        # Format the result for Redis
        result = {
            "request_id": request_id,
            "content": answer,
            "usage": json.dumps(usage),
            "model": model,
            "question": question,
            "timestamp": str(time.time())
        }
        
        # Publish to result stream
        redis_client.xadd(RESULT_STREAM, result)
        api_logger.info(f"Published question result for request {request_id}")
        
        return True
    
    except Exception as e:
        log_error(f"Error processing question request {request_id}", e)
        
        # Publish error result
        error_result = {
            "request_id": request_id,
            "error": str(e),
            "timestamp": str(time.time())
        }
        redis_client.xadd(RESULT_STREAM, error_result)
        return False

# Fix the incomplete while loop in your worker function
async def worker():
    """Main worker function to process messages from Redis streams"""
    # Create consumer groups if they don't exist
    try:
        redis_client.xgroup_create(SUMMARY_STREAM, "llm_workers", mkstream=True)
    except redis.exceptions.ResponseError:
        # Group already exists
        pass
        
    try:
        redis_client.xgroup_create(QUESTION_STREAM, "llm_workers", mkstream=True)
    except redis.exceptions.ResponseError:
        # Group already exists
        pass
    
    consumer_name = f"worker-{os.getpid()}"
    api_logger.info(f"Starting LLM worker {consumer_name}")
    
    while True:
        try:
            # Process pending messages first
            pending_summary = redis_client.xpending(SUMMARY_STREAM, "llm_workers")
            pending_question = redis_client.xpending(QUESTION_STREAM, "llm_workers")
            
            # Read new messages from the streams
            streams = {SUMMARY_STREAM: '>', QUESTION_STREAM: '>'}
            results = redis_client.xreadgroup("llm_workers", consumer_name, streams, count=1, block=1000)
            
            for stream_name, messages in results:
                for message_id, data in messages:
                    if stream_name == SUMMARY_STREAM:
                        await process_summary_request(data)
                    elif stream_name == QUESTION_STREAM:
                        await process_question_request(data)
                    
                    # Acknowledge that we processed the message
                    redis_client.xack(stream_name, "llm_workers", message_id)
        
        except Exception as e:
            log_error("Error in LLM worker", e)
            await asyncio.sleep(5)  # Wait before retrying

if __name__ == "__main__":
    # Run the worker
    asyncio.run(worker())