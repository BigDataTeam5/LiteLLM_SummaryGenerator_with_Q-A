#!/usr/bin/env python3
import os
import sys
import json
import uuid
import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
import redis.asyncio as redis_async
from dotenv import load_dotenv
import traceback

# Fix the Python path to correctly find modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("llm_worker")

# Load environment variables
load_dotenv()

# Import LLM extraction modules
from llm_extractor.litellm_query_generator import (
    summarize_markdown as litellm_summarize_markdown,
    qa_markdown as litellm_qa_markdown,
    MODEL_CONFIGS,
    generate_llm_response
)

# Stream names - ensuring they match with main.py
SUMMARY_STREAM = "summary_requests"
QUESTION_STREAM = "question_requests"
RESULT_STREAM = "llm_results"

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_DB = int(os.getenv("REDIS_DB", 0))

class LLMWorker:
    """Worker class for processing LLM requests from Redis streams."""
    
    def __init__(self):
        """Initialize the worker with Redis connection."""
        self.redis = None
    
    async def connect_redis(self):
        """Connect to Redis server."""
        try:
            self.redis = redis_async.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True
            )
            ping = await self.redis.ping()
            if ping:
                logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            else:
                logger.error(f"Failed to ping Redis at {REDIS_HOST}:{REDIS_PORT}")
            return ping
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    async def initialize_streams(self):
        """Ensure all required Redis streams and consumer groups exist."""
        try:
            # Create consumer groups for each stream
            streams = [SUMMARY_STREAM, QUESTION_STREAM, RESULT_STREAM]
            
            for stream in streams:
                try:
                    # Create the stream if it doesn't exist
                    await self.redis.xadd(stream, {"init": "stream-creation"}, maxlen=10)
                    logger.info(f"Initialized Redis stream: {stream}")
                    
                    # Create consumer group
                    await self.redis.xgroup_create(stream, "llm_workers", mkstream=True, id="0")
                    logger.info(f"Created consumer group for stream: {stream}")
                except redis_async.ResponseError as e:
                    if "BUSYGROUP" in str(e):
                        logger.info(f"Consumer group already exists for stream: {stream}")
                    else:
                        logger.error(f"Error creating consumer group for {stream}: {e}")
        except Exception as e:
            logger.error(f"Error initializing streams: {e}")
    
    async def process_request(self, request_data: Dict[str, Any], stream_name: str):
        """Process a single LLM request."""
        request_id = request_data.get("request_id", str(uuid.uuid4()))
        logger.info(f"Processing request {request_id} from stream {stream_name}")
        
        # Get task type based on stream name
        task_type = "summary" if stream_name == SUMMARY_STREAM else "qa"
        
        logger.info(f"Task type: {task_type}")
        model_id = request_data.get("model", request_data.get("model_id", "gemini"))
        content_type = request_data.get("content_type", "markdown")
        logger.info(f"Using model: {model_id}, Content type: {content_type}")
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            if task_type == "summary":
                # Process markdown summary request
                content = request_data.get("content")
                if not content:
                    return {
                        "request_id": request_id,
                        "status": "error",
                        "error": "Content is required for summarization"
                    }
                
                logger.info(f"Summarizing markdown content with {model_id}")
                result = await asyncio.to_thread(
                    litellm_summarize_markdown,
                    content,
                    model_id
                )
                
            elif task_type == "qa":
                # Process Q&A request
                content = request_data.get("content")
                if not content:
                    return {
                        "request_id": request_id,
                        "status": "error",
                        "error": "Content is required for Q&A"
                    }
                
                question = request_data.get("question")
                if not question:
                    return {
                        "request_id": request_id,
                        "status": "error",
                        "error": "Question is required for Q&A tasks"
                    }
                
                logger.info(f"Answering question with {model_id}")
                result = await asyncio.to_thread(
                    litellm_qa_markdown,
                    content,
                    question,
                    model_id
                )
                
            else:
                return {
                    "request_id": request_id,
                    "status": "error",
                    "error": f"Invalid task type: {task_type}"
                }
            
            processing_time = asyncio.get_event_loop().time() - start_time
            logger.info(f"Processed {task_type} request {request_id} in {processing_time:.2f}s")
            
            # Prepare response based on task type
            response = {
                "request_id": request_id,
                "status": "completed",
                "model_id": model_id,
                "model_name": MODEL_CONFIGS.get(model_id, {"name": model_id})["name"],
                "content_type": content_type,
                "task_type": task_type,
                "processing_time_seconds": processing_time
            }
            
            # Add task-specific fields
            if task_type == "summary":
                response["summary"] = result
            elif task_type == "qa":
                response["question"] = request_data.get("question")
                response["answer"] = result
            
            return response
        
        except Exception as e:
            logger.error(f"Error processing {task_type} request: {e}")
            logger.error(traceback.format_exc())
            return {
                "request_id": request_id,
                "status": "error",
                "error": str(e)
            }
    
    async def add_response_to_stream(self, response_data: Dict[str, Any]):
        """Add processing result to the response stream."""
        try:
            # Convert any non-string values to strings for Redis
            redis_data = {}
            for k, v in response_data.items():
                if v is not None:
                    redis_data[k] = str(v) if not isinstance(v, str) else v
            
            # Add to result stream
            await self.redis.xadd(RESULT_STREAM, redis_data, maxlen=1000)
            logger.info(f"Added result for request {response_data.get('request_id')} to {RESULT_STREAM}")
            return True
        except Exception as e:
            logger.error(f"Failed to add response to stream: {e}")
            return False
    
    async def process_stream(self):
        """Process requests from all Redis streams."""
        await self.initialize_streams()
        
        logger.info(f"Starting to process requests from streams: {SUMMARY_STREAM}, {QUESTION_STREAM}")
        consumer_name = f"worker-{uuid.uuid4()}"
        logger.info(f"Consumer name: {consumer_name}")
        
        while True:
            try:
                # Read new messages from both streams
                streams = await self.redis.xreadgroup(
                    "llm_workers", 
                    consumer_name,
                    {
                        SUMMARY_STREAM: ">", 
                        QUESTION_STREAM: ">"
                    }, 
                    count=1,
                    block=5000
                )
                
                if not streams:
                    # No new messages, continue waiting
                    await asyncio.sleep(0.1)
                    continue
                
                # Process each received stream and message
                for stream_data in streams:
                    stream_name = stream_data[0]
                    messages = stream_data[1]
                    
                    for message_id, fields in messages:
                        # Process message
                        request_data = {k: v for k, v in fields.items()}
                        
                        logger.info(f"Received request {request_data.get('request_id', 'unknown')} from {stream_name}")
                        
                        # Process the request
                        response_data = await self.process_request(request_data, stream_name)
                        
                        # Add the result to the response stream
                        await self.add_response_to_stream(response_data)
                        
                        # Acknowledge the message
                        await self.redis.xack(stream_name, "llm_workers", message_id)
                        
                        logger.info(f"Completed request {request_data.get('request_id', 'unknown')} from {stream_name}")
            
            except Exception as e:
                logger.error(f"Error processing stream: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)
                
    async def run(self):
        """Run the worker."""
        connected = await self.connect_redis()
        if not connected:
            logger.error("Failed to connect to Redis. Exiting.")
            return False
        
        await self.process_stream()
        return True

async def main():
    """Main entry point."""
    logger.info("Starting LLM Worker")
    worker = LLMWorker()
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())