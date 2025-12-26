import os
import json
from typing import Dict, List, Optional, TypedDict, Annotated
# Linter warnings for these imports are false positives - packages are installed and working correctly
from langchain_openai import ChatOpenAI  # type: ignore
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage  # type: ignore
from langgraph.graph import StateGraph, END  # type: ignore
from langgraph.graph.message import add_messages  # type: ignore
from langgraph.prebuilt import ToolNode  # type: ignore
from langchain_core.tools import tool  # type: ignore
from service.browserbase_service import BrowserbaseService
from service.twelvelabs_service import TwelveLabsService
import uuid


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_query: str
    intent: Optional[str]  # "find_videos" | "analyze" | "index" | "unknown"
    found_videos: Optional[List[Dict]]
    selected_videos: Optional[List[Dict]]
    video_id: Optional[str]
    analysis_result: Optional[str]
    index_id: Optional[str]
    conversation_context: Dict


class AgenticService:
    """
    Agentic service using LangGraph for intelligent video discovery, indexing, and analysis.
    """
    
    def __init__(self,
                 openai_api_key: Optional[str] = None,
                 browserbase_api_key: Optional[str] = None,
                 browserbase_project_id: Optional[str] = None):
        self.openai_api_key = openai_api_key or os.environ.get('OPENAI_API_KEY', '')
        self.browserbase_api_key = browserbase_api_key or os.environ.get('BROWSERBASE_API_KEY', '')
        self.browserbase_project_id = browserbase_project_id or os.environ.get('BROWSERBASE_PROJECT_ID', '')
        self.index_id = os.environ.get('TWELVELABS_INDEX_ID', '')
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        
        # Initialize services
        self.browserbase_service = None
        if self.browserbase_api_key and self.browserbase_project_id:
            self.browserbase_service = BrowserbaseService(
                browserbase_api_key=self.browserbase_api_key,
                browserbase_project_id=self.browserbase_project_id,
                openai_api_key=self.openai_api_key
            )
        
        self.twelvelabs_service = TwelveLabsService()
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.1,
            api_key=self.openai_api_key
        )
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("classify_intent", self._classify_intent)
        workflow.add_node("find_videos", self._find_videos)
        workflow.add_node("ask_indexing", self._ask_indexing)
        workflow.add_node("index_videos", self._index_videos)
        workflow.add_node("analyze_video", self._analyze_video)
        workflow.add_node("respond", self._respond)
        
        # Set entry point
        workflow.set_entry_point("classify_intent")
        
        # Add edges based on intent
        workflow.add_conditional_edges(
            "classify_intent",
            self._route_after_classify,
            {
                "chat": "respond",  # Go directly to respond for chat queries
                "find_videos": "find_videos",
                "find_and_index": "find_videos",  # Find first, then index
                "analyze": "analyze_video",
                "index": "index_videos"
            }
        )
        
        # After finding videos, check if we should index or just respond
        workflow.add_conditional_edges(
            "find_videos",
            self._route_after_find_videos,
            {
                "index": "ask_indexing",
                "respond": "respond"
            }
        )
        
        # Route after asking about indexing
        workflow.add_conditional_edges(
            "ask_indexing",
            self._route_after_ask_indexing,
            {
                "index": "index_videos",
                "skip": "respond"
            }
        )
        
        # After indexing, respond
        workflow.add_edge("index_videos", "respond")
        
        # After analysis, respond
        workflow.add_edge("analyze_video", "respond")
        
        # Respond is the end
        workflow.add_edge("respond", END)
        
        return workflow.compile()
    
    def _classify_intent(self, state: AgentState) -> AgentState:
        """Classify user intent using LLM."""
        user_query = state.get("user_query", "")
        conversation_context = state.get("conversation_context", {})
        
        system_prompt = """You are an intelligent assistant that helps users with YouTube video operations.
Your task is to classify the user's intent from their query.

Possible intents:
1. "chat" - User is asking questions about capabilities, greetings, general conversation (e.g., "What can you do?", "Hello", "How does this work?", "What actions are available?")
2. "find_videos" - User wants to ONLY search for/find YouTube videos and see the list (e.g., "find videos about AI", "search for Python tutorials", "show me videos")
3. "find_and_index" - User wants to find videos AND index them (e.g., "find and index videos", "find videos and add them", "search for videos and save them")
4. "analyze" - User wants to analyze an already indexed video (e.g., "analyze video X", "what's in video Y", "summarize video Z")
5. "index" - User explicitly wants to index videos that are already known (e.g., "index these videos", "add to index")

IMPORTANT: 
- Questions about capabilities, greetings, or general questions should use "chat"
- If the user only asks to "find" or "search" videos without mentioning indexing/saving/adding, use "find_videos"
- Only use "find_and_index" if the user explicitly mentions both finding AND indexing/saving/adding
- If a video_id is mentioned, it's likely an analyze request

Respond with ONLY the intent name (one of: chat, find_videos, find_and_index, analyze, index)."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User query: {user_query}\n\nConversation context: {json.dumps(conversation_context, indent=2)}")
        ]
        
        response = self.llm.invoke(messages)
        intent = response.content.strip().lower()
        
        # Validate intent
        if intent not in ["chat", "find_videos", "find_and_index", "analyze", "index"]:
            intent = "chat"  # Default to chat for unknown queries
        
        state["intent"] = intent
        # Don't add intent classification message - keep it internal
        
        return state
    
    def _find_videos(self, state: AgentState) -> AgentState:
        """Find videos using Browserbase service."""
        user_query = state.get("user_query", "")
        
        if not self.browserbase_service:
            state["messages"].append(AIMessage(
                content="Error: Browserbase service not configured. Cannot find videos."
            ))
            state["found_videos"] = []
            return state
        
        try:
            # Extract search query from user message - simple extraction without OpenAI
            search_query = user_query
            
            # Remove common prefixes and phrases
            import re
            prefixes_to_remove = [
                r'^find\s+videos?\s+(?:about|on|for|explaining)?\s*',
                r'^search\s+for\s+videos?\s+(?:about|on|for)?\s*',
                r'^show\s+me\s+videos?\s+(?:about|on|for)?\s*',
                r'^get\s+videos?\s+(?:about|on|for)?\s*',
                r'^videos?\s+(?:about|on|for|explaining)?\s*',
                r'^find\s+',
                r'^search\s+',
            ]
            
            for pattern in prefixes_to_remove:
                search_query = re.sub(pattern, '', search_query, flags=re.IGNORECASE)
            
            search_query = search_query.strip()
            
            # If extraction resulted in empty or very short query, use original
            if not search_query or len(search_query) < 2:
                search_query = user_query
            
            # Extract number of videos from query (default: 3)
            max_videos = 3  # Default
            import re
            # Look for patterns like "5 videos", "find 10", "show me 7", etc.
            number_patterns = [
                r'(\d+)\s*videos?',
                r'find\s+(\d+)',
                r'show\s+me\s+(\d+)',
                r'get\s+(\d+)',
                r'(\d+)\s+results?'
            ]
            
            for pattern in number_patterns:
                match = re.search(pattern, user_query.lower())
                if match:
                    try:
                        max_videos = int(match.group(1))
                        # Limit to reasonable range (1-20)
                        max_videos = max(1, min(20, max_videos))
                        break
                    except ValueError:
                        pass
            
            # Find videos
            status_callback = getattr(self, '_current_status_callback', None)
            videos = self.browserbase_service.discover_youtube_videos(
                search_query, 
                max_videos=max_videos,
                status_callback=status_callback
            )
            
            state["found_videos"] = videos
            
            # Format response based on intent
            intent = state.get("intent", "")
            if intent == "find_videos":
                # Just finding videos - format nicely for display
                if videos:
                    video_list = "\n".join([
                        f"{i+1}. **{v.get('title', 'Unknown')}**\n   URL: {v.get('url', 'N/A')}"
                        + (f"\n   Duration: {v.get('duration')}" if v.get('duration') else "")
                        + (f"\n   Channel: {v.get('channelName')}" if v.get('channelName') else "")
                        for i, v in enumerate(videos)
                    ])
                    state["messages"].append(AIMessage(
                        content=f"I found {len(videos)} video(s) for your search:\n\n{video_list}"
                    ))
                else:
                    state["messages"].append(AIMessage(
                        content="I couldn't find any videos matching your search. Please try a different query."
                    ))
            else:
                # Finding and indexing - simpler format
                state["messages"].append(AIMessage(
                    content=f"Found {len(videos)} videos:\n" + 
                    "\n".join([f"{i+1}. {v.get('title', 'Unknown')} - {v.get('url', 'N/A')}" 
                              for i, v in enumerate(videos)])
                ))
            
        except Exception as e:
            error_msg = f"Error finding videos: {str(e)}"
            state["messages"].append(AIMessage(content=error_msg))
            state["found_videos"] = []
            # Notify status callback about error if available
            status_callback = getattr(self, '_current_status_callback', None)
            if status_callback:
                try:
                    status_callback("error", error_msg)
                except Exception:
                    pass  # Don't let callback errors break the flow
        
        return state
    
    def _ask_indexing(self, state: AgentState) -> AgentState:
        """Ask user if they want to index the found videos."""
        found_videos = state.get("found_videos", [])
        
        if not found_videos:
            # No videos found, skip indexing question
            state["selected_videos"] = []
            return state
        
        # Check if user already mentioned wanting to index
        user_query = state.get("user_query", "").lower()
        intent = state.get("intent", "")
        conversation_context = state.get("conversation_context", {})
        
        # Only auto-index if intent is "find_and_index" or user explicitly mentioned indexing
        wants_to_index = any(word in user_query for word in ["index", "add", "save", "store", "analyze later"])
        dont_index = any(word in user_query for word in ["don't index", "dont index", "no index", "skip index"])
        
        # If intent is find_and_index, we should index
        should_auto_index = (intent == "find_and_index") or wants_to_index
        
        if dont_index:
            # User explicitly doesn't want to index
            state["selected_videos"] = []
            video_list = "\n".join([
                f"{i+1}. {v.get('title', 'Unknown')} - {v.get('url', 'N/A')}"
                for i, v in enumerate(found_videos[:5])
            ])
            state["messages"].append(AIMessage(
                content=f"I found {len(found_videos)} videos:\n\n{video_list}\n\n"
                       f"Videos are not indexed. You can ask me to index them later if needed."
            ))
        elif should_auto_index:
            # User wants to index (explicitly mentioned or intent is find_and_index)
            state["selected_videos"] = found_videos
            video_list = "\n".join([
                f"{i+1}. {v.get('title', 'Unknown')}"
                for i, v in enumerate(found_videos[:3])
            ])
            state["messages"].append(AIMessage(
                content=f"I found {len(found_videos)} videos:\n\n{video_list}\n\n"
                       f"I'll index these videos for you so you can analyze them later. Processing..."
            ))
        else:
            # Ask user if they want to index (shouldn't happen with new routing, but keep as fallback)
            video_list = "\n".join([
                f"{i+1}. {v.get('title', 'Unknown')} - {v.get('url', 'N/A')}"
                for i, v in enumerate(found_videos[:3])  # Show first 3
            ])
            
            state["messages"].append(AIMessage(
                content=f"I found {len(found_videos)} videos:\n\n{video_list}\n\n"
                       f"Would you like me to index these videos so you can analyze them later? "
                       f"(Say 'yes' or 'index them' to proceed, or 'no' to skip)"
            ))
            
            # Don't auto-index if user hasn't explicitly asked
            state["selected_videos"] = []
        
        return state
    
    def _route_after_find_videos(self, state: AgentState) -> str:
        """Route after finding videos - check if we should index or just respond."""
        intent = state.get("intent", "")
        
        # If intent is "find_and_index", proceed to ask about indexing
        if intent == "find_and_index":
            # Set selected_videos so indexing will proceed
            found_videos = state.get("found_videos", [])
            state["selected_videos"] = found_videos
            return "index"
        
        # If intent is just "find_videos", go directly to respond (don't index)
        return "respond"
    
    def _route_after_ask_indexing(self, state: AgentState) -> str:
        """Route after asking about indexing."""
        selected_videos = state.get("selected_videos", [])
        
        # If videos are selected, proceed to index
        if selected_videos:
            return "index"
        else:
            # No videos selected, skip indexing
            return "skip"
    
    def _index_videos(self, state: AgentState) -> AgentState:
        """Index selected videos."""
        selected_videos = state.get("selected_videos", [])
        
        if not selected_videos:
            state["messages"].append(AIMessage(content="No videos selected for indexing."))
            return state
        
        if not self.index_id:
            state["messages"].append(AIMessage(
                content="Error: TWELVELABS_INDEX_ID not configured. Cannot index videos."
            ))
            return state
        
        indexed_results = []
        failed_results = []
        
        for video in selected_videos:
            try:
                video_url = video.get("url", "")
                if not video_url:
                    continue
                
                # Check if already indexed
                existing_video_id = self.twelvelabs_service.find_video_by_url(self.index_id, video_url)
                if existing_video_id:
                    indexed_results.append({
                        "video": video,
                        "video_id": existing_video_id,
                        "status": "already_indexed"
                    })
                    continue
                
                # Download and index
                import os
                import re
                temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_videos')
                os.makedirs(temp_dir, exist_ok=True)
                
                video_id_match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11}).*', video_url)
                yt_video_id = video_id_match.group(1) if video_id_match else str(uuid.uuid4())
                unique_id = uuid.uuid4().hex[:8]
                video_path = os.path.join(temp_dir, f"yt_{yt_video_id}_{unique_id}.mp4")
                
                from utils.video_downloader import download_youtube_video
                downloaded_path = download_youtube_video(video_url, video_path)
                
                result = self.twelvelabs_service.upload_video_file(
                    index_id=self.index_id,
                    file_path=downloaded_path
                )
                
                # Clean up
                try:
                    if os.path.exists(downloaded_path):
                        os.remove(downloaded_path)
                except:
                    pass
                
                if 'error' not in result and result.get("video_id"):
                    indexed_results.append({
                        "video": video,
                        "video_id": result.get("video_id"),
                        "status": "indexed"
                    })
                else:
                    failed_results.append({
                        "video": video,
                        "error": result.get("error", "Unknown error")
                    })
                    
            except Exception as e:
                failed_results.append({
                    "video": video,
                    "error": str(e)
                })
        
        # Build response
        response_parts = []
        if indexed_results:
            response_parts.append(f"Successfully indexed {len(indexed_results)} video(s):")
            for result in indexed_results:
                video_title = result["video"].get("title", "Unknown")
                video_id = result["video_id"]
                status = result["status"]
                response_parts.append(f"- {video_title} (ID: {video_id}, Status: {status})")
        
        if failed_results:
            response_parts.append(f"\nFailed to index {len(failed_results)} video(s):")
            for result in failed_results:
                video_title = result["video"].get("title", "Unknown")
                error = result["error"]
                response_parts.append(f"- {video_title} (Error: {error})")
        
        state["messages"].append(AIMessage(content="\n".join(response_parts)))
        
        return state
    
    def _analyze_video(self, state: AgentState) -> AgentState:
        """Analyze a video using TwelveLabs."""
        user_query = state.get("user_query", "")
        conversation_context = state.get("conversation_context", {})
        
        # Extract video_id from query or context
        video_id = conversation_context.get("video_id")
        
        if not video_id:
            # Try to extract from query
            extract_prompt = f"""Extract the video ID from this query: "{user_query}"

Look for:
- TwelveLabs video IDs (alphanumeric strings)
- YouTube URLs (extract video ID from watch?v=...)
- References to previously mentioned videos

If found, return ONLY the video ID. If not found, return "NOT_FOUND".

Video ID:"""
            
            messages = [
                SystemMessage(content="Extract video ID from user query."),
                HumanMessage(content=extract_prompt)
            ]
            
            response = self.llm.invoke(messages)
            video_id = response.content.strip()
            
            if video_id == "NOT_FOUND" or not video_id:
                state["messages"].append(AIMessage(
                    content="I couldn't find a video ID in your query. Please provide a video ID or URL to analyze."
                ))
                return state
        
        # Extract analysis prompt
        analysis_prompt = user_query
        if "analyze" in user_query.lower() or "what" in user_query.lower():
            # Keep the query as the prompt
            pass
        else:
            analysis_prompt = f"Analyze this video: {user_query}"
        
        try:
            # Perform analysis
            result = self.twelvelabs_service.analyze_video(video_id, analysis_prompt)
            state["analysis_result"] = result
            state["video_id"] = video_id
            state["messages"].append(AIMessage(content=f"Analysis result:\n{result}"))
        except Exception as e:
            state["messages"].append(AIMessage(content=f"Error analyzing video: {str(e)}"))
        
        return state
    
    def _route_after_classify(self, state: AgentState) -> str:
        """Route based on classified intent."""
        intent = state.get("intent", "chat")
        # Ensure valid intent
        if intent not in ["chat", "find_videos", "find_and_index", "analyze", "index"]:
            intent = "chat"
        return intent
    
    def _respond(self, state: AgentState) -> AgentState:
        """Generate final response."""
        intent = state.get("intent", "")
        user_query = state.get("user_query", "")
        messages = state.get("messages", [])
        
        # For chat queries, generate an intelligent conversational response
        if intent == "chat":
            system_prompt = """You are a helpful AI assistant that helps users with YouTube video operations.
You can:
1. Find and search for YouTube videos based on queries
2. Index videos so they can be analyzed later
3. Analyze already indexed videos to answer questions about their content
4. Provide information about your capabilities

Be friendly, concise, and helpful. If the user asks about your capabilities, explain what you can do clearly.
Answer their question directly and naturally."""
            
            chat_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query)
            ]
            
            response = self.llm.invoke(chat_messages)
            state["messages"].append(AIMessage(content=response.content))
        else:
            # For other intents, the response is already in the messages
            # Don't duplicate it - just ensure we have a response
            if not messages or not any(isinstance(m, AIMessage) for m in messages):
                # If no AI message exists, create a default response
                state["messages"].append(AIMessage(content="I've processed your request."))
        
        return state
    
    def process_query(self, user_query: str, conversation_context: Optional[Dict] = None, status_callback=None) -> Dict:
        """
        Process a user query through the agentic workflow.
        
        Args:
            user_query: The user's query/request
            conversation_context: Optional conversation context (video_id, previous messages, etc.)
            status_callback: Optional callback function(status, message) for status updates
        
        Returns:
            Dict with response and state information
        """
        # Store status_callback temporarily for use in graph nodes
        self._current_status_callback = status_callback
        
        if conversation_context is None:
            conversation_context = {}
        
        initial_state = {
            "messages": [HumanMessage(content=user_query)],
            "user_query": user_query,
            "intent": None,
            "found_videos": None,
            "selected_videos": None,
            "video_id": None,
            "analysis_result": None,
            "index_id": self.index_id,
            "conversation_context": conversation_context
        }
        
        # Run the graph
        final_state = self.graph.invoke(initial_state)
        
        # Extract response - get the last AI message (most recent response)
        messages = final_state.get("messages", [])
        response_text = ""
        # Get the last AI message (most recent response)
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                response_text = msg.content
                break
        
        # Build result with only non-null values
        result = {
            "response": response_text
        }
        
        # Only include fields that have values
        intent = final_state.get("intent")
        if intent:
            result["intent"] = intent
        
        found_videos = final_state.get("found_videos")
        if found_videos:
            result["found_videos"] = found_videos
        
        video_id = final_state.get("video_id")
        if video_id:
            result["video_id"] = video_id
        
        analysis_result = final_state.get("analysis_result")
        if analysis_result:
            result["analysis_result"] = analysis_result
        
        indexed_videos = final_state.get("selected_videos")
        if indexed_videos:
            result["indexed_videos"] = indexed_videos
        
        # Clean up status callback
        try:
            if hasattr(self, '_current_status_callback'):
                delattr(self, '_current_status_callback')
        except Exception:
            pass  # Ignore cleanup errors
        
        return result

