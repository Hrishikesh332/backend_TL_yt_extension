# YouTube Extension - Flask API


## Base URL
```
http://localhost:5000
```

## Endpoints

### 1. Agentic Chat (NEW - Recommended)

**Endpoint:** `POST /api/agentic-chat`

**Description:** Agentic API that understands user intent and automatically routes to find videos, index them, or analyze existing videos. Uses LangGraph for state management and OpenAI for query understanding.

**Required Environment Variables:**
- `OPENAI_API_KEY` - Your OpenAI API key (required)
- `BROWSERBASE_API_KEY` - Your Browserbase API key (for finding videos)
- `BROWSERBASE_PROJECT_ID` - Your Browserbase project ID
- `TWELVELABS_INDEX_ID` - Your TwelveLabs index ID (for indexing/analysis)

**Request Body:**
```json
{
  "query": "find videos about machine learning and index them",
  "conversation_context": {
    "auto_index": true,
    "video_id": "optional_video_id"
  }
}
```

**Request Parameters:**
- `query` (required) - Natural language query describing what you want
- `conversation_context` (optional) - Context from previous conversations
  - `auto_index` (optional, default: true) - Automatically index found videos
  - `video_id` (optional) - Video ID for analysis requests

**Success Response:**
```json
{
  "status": "success",
  "response": "I found 5 videos about machine learning. I'll index them for you...",
  "intent": "find_videos",
  "found_videos": [
    {
      "title": "Machine Learning Tutorial",
      "url": "https://www.youtube.com/watch?v=...",
      "channelName": "Tech Channel",
      "duration": "10:30"
    }
  ],
  "indexed_videos": [...],
  "video_id": "...",
  "analysis_result": "..."
}
```

**Streaming Endpoint:** `POST /api/agentic-chat/stream`

Returns streaming responses as the agent processes your request.

**Notes**
- Uses LangGraph for intelligent workflow orchestration
- Automatically understands intent (find, analyze, index)
- After finding videos, asks if you want to index them (unless auto_index is false)
- Can handle conversational follow ups
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

