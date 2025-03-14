# Understanding worker.py

This worker.py file implements a background processing system that handles LLM (Large Language Model) tasks using Redis streams as a message queue. Let me explain the key components:

## 1. Redis Streams Architecture

The worker uses Redis streams as a robust message queue system with these components:

- **Three streams:**
  - `summary_requests` - Incoming summarization tasks
  - `question_requests` - Incoming question answering tasks
  - `llm_results` - Stream where results are published

- **Consumer groups:** The worker creates consumer groups to ensure reliable message processing even with multiple worker instances.

## 2. Model Management

- **Model mapping:** The code maps user-friendly model names to actual model identifiers:
  ```python
  model_mapping = {
      "chatgpt": "gpt-4o", 
      "claude": "anthropic.claude-3-opus-20240229",
      "grok": "xai.grok-1",
      "gemini": "gemini/gemini-1.5-flash",
      "deepseek": "deepseek-ai/deepseek-chat"
  }
  ```

- **API Key management:** API keys for different providers are stored in environment variables and mapped to models.

## 3. Request Processing Functions

- `process_summary_request(data)`: Takes content to summarize and:
  1. Gets the appropriate model and API key
  2. Formats the request with system and user messages
  3. Calls the LLM through LiteLLM
  4. Extracts the summary and usage statistics
  5. Publishes results back to the result stream

- `process_question_request(data)`: Similar flow but for answering questions about content.

## 4. Main Worker Loop

The `worker()` function:
1. Creates consumer groups if they don't exist
2. Sets up a unique consumer name
3. Continuously polls both streams for new messages
4. Routes messages to the appropriate processing function
5. Acknowledges processed messages
6. Handles any errors that occur during processing

## How it Works in the Application

1. Your API endpoints receive requests from users
2. The API adds these requests to the appropriate Redis stream
3. The worker(s) pick up these messages, process them with LLMs
4. Results are published back to a results stream
5. The API can then retrieve and return these results to users

This architecture allows your application to handle computationally expensive LLM operations asynchronously, preventing API endpoint timeouts and enabling better scalability.