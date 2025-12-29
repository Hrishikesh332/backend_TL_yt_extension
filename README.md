# YouTube Extension - Flask API


## Base URL
```
http://localhost:5000
```

## Endpoints

### 1. Agentic Chat (NEW - Recommended)

**Endpoint:** `POST /api/agentic-chat`

**Description:** Agentic API that understands user intent and routes to find videos, index them, or analyze existing videos. Uses LangGraph for state management and OpenAI for query understanding.

**Workflow:**
1. **Find Videos**: When you search for videos, the API finds them and displays the results
2. **Ask for Confirmation**: After showing videos, the API asks if you want to index them
3. **Index on Confirmation**: Only indexes videos when you explicitly confirm (e.g., "yes", "index them")

**Required Environment Variables:**
- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `BROWSERBASE_API_KEY` - Your Browserbase API key (for finding videos)
- `BROWSERBASE_PROJECT_ID` - Your Browserbase project ID
- `TWELVELABS_INDEX_ID` - Your TwelveLabs index ID (for indexing/analysis)

**Request Body:**
```json
{
  "query": "find videos about machine learning",
  "conversation_context": {
    "found_videos": [],
    "video_id": "optional_video_id"
  }
}
```

**Request Parameters:**
- `query` (required) - Natural language query describing what you want
- `conversation_context` (optional) - Context from previous conversations
  - `found_videos` (optional) - Previously found videos (used when confirming indexing)
  - `video_id` (optional) - Video ID for analysis requests

**Success Response (After Finding Videos):**
```json
{
  "status": "success",
  "response": "I found 3 video(s) for your search:\n\n1. **Machine Learning Tutorial**\n   URL: https://www.youtube.com/watch?v=...\n   Duration: 10:30\n   Channel: Tech Channel\n\n**Would you like me to index these videos so you can analyze them later?**\nReply 'yes' or 'index them' to proceed with indexing.",
  "intent": "find_videos",
  "found_videos": [
    {
      "title": "Machine Learning Tutorial",
      "url": "https://www.youtube.com/watch?v=...",
      "channelName": "Tech Channel",
      "duration": "10:30"
    }
  ]
}
```

**Success Response (After Confirming Indexing):**
```json
{
  "status": "success",
  "response": "✅ Successfully indexed 3 video(s):\n  • Machine Learning Tutorial\n    Video ID: abc123 (indexed)\n\n💡 You can now analyze these videos by asking questions about them!",
  "intent": "index",
  "indexed_videos": [...]
}
```

**Streaming Endpoint:** `POST /api/agentic-chat/stream`

Returns real time Server Sent Events as the agent processes your request. Provides status updates during video discovery, indexing, and analysis.

**Request Body:**
```json
{
  "query": "find videos about machine learning",
  "conversation_context": {
    "found_videos": [],
    "video_id": "optional_video_id"
  }
}
```

**Response Format:** Server-Sent Events (SSE) stream

**Status Updates:**
- `starting` - Request processing initiated
- `info` - Informational updates (search query, video count, metadata fetching)
- `completed` - Final response with results
- `error` - Error occurred during processing

**Real SSE Event Example:**
```
data: {"status": "starting", "message": "Processing your request...", "timestamp": "2025-12-28T14:23:45.123456"}

data: {"status": "starting", "message": "Starting browser automation to find YouTube videos...", "timestamp": "2025-12-28T14:23:45.234567"}

data: {"status": "info", "message": "Search query: 'machine learning tutorials'", "timestamp": "2025-12-28T14:23:45.345678"}

data: {"status": "info", "message": "Max videos to find: 3", "timestamp": "2025-12-28T14:23:45.456789"}

data: {"status": "info", "message": "Creating Browserbase session...", "timestamp": "2025-12-28T14:23:46.123456"}

data: {"status": "info", "message": "Navigating to YouTube...", "timestamp": "2025-12-28T14:23:47.234567"}

data: {"status": "info", "message": "Searching for: 'machine learning tutorials'", "timestamp": "2025-12-28T14:23:48.345678"}

data: {"status": "info", "message": "Waiting for search results...", "timestamp": "2025-12-28T14:23:49.456789"}

data: {"status": "info", "message": "Extracting video information...", "timestamp": "2025-12-28T14:23:52.123456"}

data: {"status": "info", "message": "Found 5 raw videos", "timestamp": "2025-12-28T14:23:53.234567"}

data: {"status": "info", "message": "Fetching metadata for video 1...", "timestamp": "2025-12-28T14:23:54.345678"}

data: {"status": "info", "message": "Fetching metadata for video 2...", "timestamp": "2025-12-28T14:23:55.456789"}

data: {"status": "completed", "response": "I found 3 video(s) for your search:\n\n1. **Machine Learning Tutorial for Beginners**\n   URL: https://www.youtube.com/watch?v=abc123\n   Duration: 15:30\n   Channel: Tech Education\n\n2. **Deep Learning Explained**\n   URL: https://www.youtube.com/watch?v=def456\n   Duration: 22:15\n   Channel: AI Academy\n\n3. **Neural Networks Crash Course**\n   URL: https://www.youtube.com/watch?v=ghi789\n   Duration: 18:45\n   Channel: Data Science Pro", "intent": "find_videos", "found_videos": [{"title": "Machine Learning Tutorial for Beginners", "url": "https://www.youtube.com/watch?v=abc123", "channelName": "Tech Education", "duration": "15:30", "thumbnailUrl": "https://i.ytimg.com/vi/abc123/hqdefault.jpg"}, {"title": "Deep Learning Explained", "url": "https://www.youtube.com/watch?v=def456", "channelName": "AI Academy", "duration": "22:15", "thumbnailUrl": "https://i.ytimg.com/vi/def456/hqdefault.jpg"}, {"title": "Neural Networks Crash Course", "url": "https://www.youtube.com/watch?v=ghi789", "channelName": "Data Science Pro", "duration": "18:45", "thumbnailUrl": "https://i.ytimg.com/vi/ghi789/hqdefault.jpg"}], "timestamp": "2025-12-28T14:24:02.123456"}
```

**Note:** Each SSE event follows the format `data: {JSON}\n\n` (data prefix, JSON payload, two newlines). The stream sends events in real-time as the agent processes your request.

**Final Response Fields:**
- `status` - "completed" or "error"
- `response` - Final response message
- `intent` - Detected intent (find_videos, analyze, index, chat)
- `found_videos` - Array of discovered videos (if applicable)
- `indexed_videos` - Array of indexed videos (if applicable)
- `video_id` - Video ID for analysis (if applicable)
- `analysis_result` - Analysis result (if applicable)
- `timestamp` - ISO timestamp of the event

**Usage Example:**
```bash
# Step 1: Find videos
curl -X POST "http://localhost:5000/api/agentic-chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "find videos about AI"}' \
  -N

# Step 2: Confirm indexing (use found_videos from previous response)
curl -X POST "http://localhost:5000/api/agentic-chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "yes index them", "conversation_context": {"found_videos": [...]}}' \
  -N
```

**Notes:**
- Uses LangGraph for intelligent workflow orchestration
- Automatically understands intent (find, analyze, index, chat)
- Provides real-time progress updates via SSE
- **Two-step process**: First shows found videos, then asks for confirmation before indexing
- Only indexes videos when user explicitly confirms (e.g., "yes", "index them")
- Combines Browserbase for video discovery and TwelveLabs for indexing/analysis

---

### 2. Find Videos

**Endpoint:** `POST /api/find-videos`

**Description:** Discovers YouTube videos using Browserbase automation. Searches YouTube and extracts video information.

**Required Environment Variables:**
- `BROWSERBASE_API_KEY` - Your Browserbase API key
- `BROWSERBASE_PROJECT_ID` - Your Browserbase project ID
- `OPENAI_API_KEY` - Your OpenAI API key (required for agentic automation)

**Request Body:**
```json
{
  "search_query": "AI technology demo",
  "max_videos": 3
}
```

**Request Parameters:**
- `search_query` (required) - YouTube search query
- `max_videos` (optional, default: 3, max: 20) - Maximum number of videos to return

**Success Response:**
```json
{
  "status": "success",
  "videos": [
    {
      "title": "Video Title",
      "url": "https://www.youtube.com/watch?v=...",
      "channelName": "Channel Name",
      "duration": "10:30"
    }
  ],
  "count": 1
}
```

```

---

### 2. Index Videos (NEW)

**Endpoint:** `POST /api/index-videos`

**Description:** Indexes one or more YouTube videos using TwelveLabs. Downloads videos and uploads them to TwelveLabs for indexing.

**Request Body (Multiple Videos):**
```json
{
  "video_urls": [
    "https://www.youtube.com/watch?v=VIDEO_ID_1",
    "https://www.youtube.com/watch?v=VIDEO_ID_2"
  ],
  "index_id": "optional_index_id"
}
```

**Request Body (Single Video):**
```json
{
  "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
  "index_id": "optional_index_id"
}
```

**Request Parameters:**
- `video_url` or `video_urls` (required) - YouTube video URL(s) to index
- `index_id` (optional) - TwelveLabs index ID (uses `TWELVELABS_INDEX_ID` from env if not provided)

**Success Response:**
```json
{
  "status": "success",
  "indexed_videos": [
    {
      "video_url": "https://www.youtube.com/watch?v=...",
      "video_id": "twelvelabs_video_id",
      "status": "indexed"
    }
  ],
  "failed_videos": [],
  "summary": {
    "total": 1,
    "indexed": 1,
    "failed": 0
  }
}
```


**Notes**
- Checks if videos are already indexed before downloading
- Downloads videos temporarily, indexes them, then cleans up
- Returns status for each video (indexed, already_indexed, or failed)

---

### 3. Health Check

**Endpoint:** `GET /api/health`

**Description:** Check if the API server is running.

**Response:**
```json
{
  "status": "healthy"
}
```

---

### 4. Download and Index Video

**Endpoint:** `POST /api/download-and-index`

**Description:** Downloads a YouTube video and indexes it with TwelveLabs for analysis.

**Request Body:**
```json
{
  "youtube_url": "https://www.youtube.com/watch?v=VIDEO_ID"
}
```

**Success Response:**
```json
{
  "status": "success",
  "video_id": "6928f5903e29e0f8db51bdab",
  "message": "Video downloaded and indexed successfully. Ready for analysis."
}
```


**Notes**
- Video is kept until indexing completes and video_id is confirmed
- Indexing may take time depending on video length
- Use the returned `video_id` for analysis requests

---

### 5. Analyze Video

**Endpoint:** `POST /api/analyze`

**Description:** Performs AI-powered analysis on an indexed video using TwelveLabs. **Always returns streaming responses** for real-time feedback.

**Request Body (Open-ended Analysis):**
```json
{
  "video_id": "6928f59xxxxxxxx",
  "prompt": "Your custom question or analysis request",
  "analysis_type": "open-ended"
}
```

**Request Body**
```json
{
  "video_id": "6928fxxxxxxx",
  "analysis_type": "summary"
}
```

**Request Parameters**
- `video_id` (required) - ID of the indexed video
- `prompt` (required for open-ended) - Custom analysis question
- `analysis_type` (optional, default: "open-ended") - Type of analysis

**Analysis Types**
- `open-ended` - Custom prompt (requires `prompt` field)
- `title` - Generate video title
- `topic` - Identify main topics
- `hashtag` - Generate relevant hashtags
- `summary` - Video summary
- `chapter` - Break video into chapters
- `highlight` - Extract key highlights


**Note:** This is TRUE server-sent streaming using TwelveLabs' `analyze_stream` API. Text appears in real-time as the AI generates it, not pre-fetched and split.


---

## Environment Setup

Required environment variables in `.env`

### Complete .env Example
```
# TwelveLabs Configuration
TWELVELABS_API_KEY=your_twelvelabs_api_key_here
TWELVELABS_INDEX_ID=your_index_id_here

# Browserbase Configuration (Required for /find-videos API)
BROWSERBASE_API_KEY=your_browserbase_api_key_here
BROWSERBASE_PROJECT_ID=your_browserbase_project_id_here

# OpenAI Configuration (REQUIRED for /find-videos API - agentic automation)
OPENAI_API_KEY=your_openai_api_key_here

# Proxy Configuration 
PROXY_URL=http://username:password@proxy_host:port

# Application Configuration (Optional)
APP_URL=http://localhost:5000
```


## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

3. Create a `.env` file with your API keys (see Environment Setup section above)

