import os
import json
import threading
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
from utils.video_processor import get_video_duration_from_file, clip_video
import uuid


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_query: str
    intent: Optional[str]
    found_videos: Optional[List[Dict]]
    selected_videos: Optional[List[Dict]]
    video_id: Optional[str]
    analysis_result: Optional[str]
    index_id: Optional[str]
    conversation_context: Dict


class AgenticService:
    
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
        
        self.browserbase_service = None
        if self.browserbase_api_key and self.browserbase_project_id:
            self.browserbase_service = BrowserbaseService(
                browserbase_api_key=self.browserbase_api_key,
                browserbase_project_id=self.browserbase_project_id
            )
        
        self.twelvelabs_service = TwelveLabsService()
        
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.1,
            api_key=self.openai_api_key
        )
        
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        workflow.add_node("classify_intent", self._classify_intent)
        workflow.add_node("find_videos", self._find_videos)
        workflow.add_node("index_videos", self._index_videos)
        workflow.add_node("analyze_video", self._analyze_video)
        workflow.add_node("respond", self._respond)
        
        workflow.set_entry_point("classify_intent")
        
        workflow.add_conditional_edges(
            "classify_intent",
            self._route_after_classify,
            {
                "chat": "respond",
                "find_videos": "find_videos",
                "index": "index_videos",
                "analyze": "analyze_video"
            }
        )
        
        # After finding videos, always respond (show videos + ask about indexing)
        workflow.add_edge("find_videos", "respond")
        
        # After indexing, respond
        workflow.add_edge("index_videos", "respond")
        
        # After analysis, respond
        workflow.add_edge("analyze_video", "respond")
        
        # Respond is the end
        workflow.add_edge("respond", END)
        
        return workflow.compile()
    
    def _classify_intent(self, state: AgentState) -> AgentState:
        user_query = state.get("user_query", "")
        conversation_context = state.get("conversation_context", {})
        
        # Check if user is confirming indexing of previously found videos
        query_lower = user_query.lower().strip()
        
        # Check for indexing confirmation patterns
        indexing_confirmations = [
            "yes", "yes index", "yes please", "index them", "index these", 
            "go ahead", "proceed", "do it", "index the videos", "yes index them",
            "index all", "index please", "sure", "ok index", "okay index",
            "yep", "yeah", "confirm", "index now"
        ]
        
        # Check if this looks like a confirmation to index
        is_index_confirmation = any(query_lower == phrase or query_lower.startswith(phrase + " ") for phrase in indexing_confirmations)
        
        # Also check if context has previously found videos
        has_previous_videos = bool(conversation_context.get("found_videos"))
        
        if is_index_confirmation and has_previous_videos:
            state["intent"] = "index"
            state["found_videos"] = conversation_context.get("found_videos", [])
            state["selected_videos"] = conversation_context.get("found_videos", [])
            return state
        
        system_prompt = """You are an intelligent assistant that helps users with YouTube video operations.
Your task is to classify the user's intent from their query.

Possible intents:
1. "chat" - User is asking questions about capabilities, greetings, general conversation
2. "find_videos" - User wants to search for/find YouTube videos (e.g., "find videos about AI", "search for tutorials")
3. "index" - User wants to index specific videos they already have URLs for (e.g., "index this video: URL", "index https://youtube.com/...")
4. "analyze" - User wants to analyze an already indexed video (e.g., "analyze video X", "what's in this video")

IMPORTANT: 
- If user just wants to "find" or "search" videos, use "find_videos"
- Only use "index" if user provides specific video URLs to index
- Questions about capabilities should use "chat"

Respond with ONLY the intent name (one of: chat, find_videos, index, analyze)."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"User query: {user_query}\n\nContext: {json.dumps(conversation_context, indent=2)}")
        ]
        
        response = self.llm.invoke(messages)
        intent = response.content.strip().lower()
        
        if intent not in ["chat", "find_videos", "index", "analyze"]:
            intent = "chat"
        
        state["intent"] = intent
        return state
    
    def _find_videos(self, state: AgentState) -> AgentState:
        user_query = state.get("user_query", "")
        
        if not self.browserbase_service:
            state["messages"].append(AIMessage(
                content="Error: Browserbase service not configured. Cannot find videos."
            ))
            state["found_videos"] = []
            return state
        
        try:
            search_query = user_query
            
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
            
            if not search_query or len(search_query) < 2:
                search_query = user_query
            
            max_videos = 3
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
                        max_videos = max(1, min(20, max_videos))
                        break
                    except ValueError:
                        pass
            
            status_callback = getattr(self, '_current_status_callback', None)
            videos = self.browserbase_service.discover_youtube_videos(
                search_query, 
                max_videos=max_videos,
                status_callback=status_callback
            )
            
            state["found_videos"] = videos
            
            # Format videos nicely and ASK about indexing
            if videos:
                video_list = "\n".join([
                    f"{i+1}. **{v.get('title', 'Unknown')}**\n   URL: {v.get('url', 'N/A')}"
                    + (f"\n   Duration: {v.get('duration')}" if v.get('duration') else "")
                    + (f"\n   Channel: {v.get('channelName')}" if v.get('channelName') else "")
                    for i, v in enumerate(videos)
                ])
                
                # Show videos AND ask about indexing
                state["messages"].append(AIMessage(
                    content=f"I found {len(videos)} video(s) for your search:\n\n{video_list}\n\n"
                           f"**Would you like me to index these videos so you can analyze them later?**\n"
                           f"Reply 'yes' or 'index them' to proceed with indexing."
                ))
            else:
                state["messages"].append(AIMessage(
                    content="I couldn't find any videos matching your search. Please try a different query."
                ))
            
        except Exception as e:
            error_msg = f"Error finding videos: {str(e)}"
            state["messages"].append(AIMessage(content=error_msg))
            state["found_videos"] = []
            status_callback = getattr(self, '_current_status_callback', None)
            if status_callback:
                try:
                    status_callback("error", error_msg)
                except Exception:
                    pass
        
        return state
    
    def _index_videos(self, state: AgentState) -> AgentState:
        selected_videos = state.get("selected_videos", [])
        conversation_context = state.get("conversation_context", {})
        
        # If no selected videos, check conversation context for previously found videos
        if not selected_videos:
            selected_videos = conversation_context.get("found_videos", [])
        
        if not selected_videos:
            state["messages"].append(AIMessage(
                content="No videos to index. Please first search for videos using 'find videos about [topic]'."
            ))
            return state
        
        if not self.index_id:
            state["messages"].append(AIMessage(
                content="Error: TWELVELABS_INDEX_ID not configured. Cannot index videos."
            ))
            return state
        
        # Send status update
        status_callback = getattr(self, '_current_status_callback', None)
        if status_callback:
            try:
                status_callback("indexing", f"Starting to index {len(selected_videos)} video(s)...")
            except Exception:
                pass
        
        indexed_results = []
        failed_results = []
        
        for idx, video in enumerate(selected_videos):
            try:
                video_url = video.get("url", "")
                if not video_url:
                    continue
                
                video_title = video.get("title", "Unknown")
                
                if status_callback:
                    try:
                        status_callback("indexing", f"Processing video {idx + 1}/{len(selected_videos)}: {video_title[:50]}...")
                    except Exception:
                        pass
                
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
                
                if status_callback:
                    try:
                        status_callback("downloading", f"Downloading: {video_title[:50]}...")
                    except Exception:
                        pass
                
                from utils.video_downloader import download_youtube_video
                downloaded_path = download_youtube_video(video_url, video_path)
                
                # Check video duration first
                duration = get_video_duration_from_file(downloaded_path)
                is_long_video = duration is not None and duration > 3600
                
                if is_long_video:
                    print(f"Video is longer than 1 hour ({duration/60:.2f} minutes), will clip and index first chunk immediately")
                    video_segments = clip_video(downloaded_path, temp_dir, segment_duration=3600)
                    print(f"Video segments created: {len(video_segments)}")
                    
                    if len(video_segments) > 1:
                        # Index first segment immediately
                        first_segment = video_segments[0]
                        if status_callback:
                            try:
                                status_callback("uploading", f"Uploading first segment to TwelveLabs: {video_title[:50]}...")
                            except Exception:
                                pass
                        
                        print(f"Indexing first segment immediately: {first_segment}")
                        result = self.twelvelabs_service.upload_video_file(
                            index_id=self.index_id,
                            file_path=first_segment
                        )
                        
                        if 'error' not in result and result.get("video_id"):
                            first_video_id = result.get("video_id")
                            print(f"First segment indexed successfully: {first_video_id}")
                            
                            # Clean up first segment file
                            if first_segment != downloaded_path and os.path.exists(first_segment):
                                try:
                                    os.remove(first_segment)
                                except:
                                    pass
                            
                            # Process remaining segments in background
                            def index_remaining_segments(segments, original_path, vid_title):
                                remaining_segments = segments[1:]
                                for segment_idx, segment_path in enumerate(remaining_segments, start=2):
                                    try:
                                        print(f"[BACKGROUND] Indexing segment {segment_idx}/{len(segments)}: {segment_path}")
                                        result = self.twelvelabs_service.upload_video_file(
                                            index_id=self.index_id,
                                            file_path=segment_path
                                        )
                                        if 'error' not in result and result.get("video_id"):
                                            print(f"[BACKGROUND] Segment {segment_idx} indexed: {result.get('video_id')}")
                                    except Exception as e:
                                        print(f"[BACKGROUND] Error indexing segment {segment_idx}: {str(e)}")
                                    finally:
                                        if segment_path != original_path and os.path.exists(segment_path):
                                            try:
                                                os.remove(segment_path)
                                            except:
                                                pass
                                
                                # Clean up original file after all segments processed
                                if os.path.exists(original_path):
                                    try:
                                        os.remove(original_path)
                                        print(f"[BACKGROUND] Original file deleted: {original_path}")
                                    except:
                                        pass
                            
                            thread = threading.Thread(
                                target=index_remaining_segments,
                                args=(video_segments, downloaded_path, video_title),
                                daemon=True
                            )
                            thread.start()
                            
                            indexed_results.append({
                                "video": video,
                                "video_id": first_video_id,
                                "video_ids": [first_video_id],
                                "chunks": [
                                    {
                                        "chunk_number": 1,
                                        "video_id": first_video_id,
                                        "status": "indexed",
                                        "time_range": "0:00:00-1:00:00"
                                    }
                                ],
                                "segments": len(video_segments),
                                "total_segments": len(video_segments),
                                "indexed_segments": 1,
                                "remaining_segments_processing": True,
                                "status": "indexed"
                            })
                        else:
                            failed_results.append({
                                "video": video,
                                "error": f"Failed to index first segment: {result.get('error', 'Unknown error')}"
                            })
                    else:
                        # Only one segment (shouldn't happen if duration > 3600, but handle it)
                        if status_callback:
                            try:
                                status_callback("uploading", f"Uploading to TwelveLabs: {video_title[:50]}...")
                            except Exception:
                                pass
                        
                        result = self.twelvelabs_service.upload_video_file(
                            index_id=self.index_id,
                            file_path=video_segments[0]
                        )
                        
                        if video_segments[0] != downloaded_path:
                            try:
                                if os.path.exists(video_segments[0]):
                                    os.remove(video_segments[0])
                            except:
                                pass
                        
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
                else:
                    # Video is 1 hour or less - process normally (no changes)
                    print(f"Video is {duration/60:.2f if duration else 'unknown'} minutes, processing normally")
                    if status_callback:
                        try:
                            status_callback("uploading", f"Uploading to TwelveLabs: {video_title[:50]}...")
                        except Exception:
                            pass
                    
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
            response_parts.append(f"✅ Successfully indexed {len(indexed_results)} video(s):")
            for result in indexed_results:
                video_title = result["video"].get("title", "Unknown")
                video_id = result["video_id"]
                status = result["status"]
                
                if result.get("chunks"):
                    chunks_info = result["chunks"]
                    total_segments = result.get("total_segments", 1)
                    indexed_segments = result.get("indexed_segments", 1)
                    
                    if total_segments > 1:
                        response_parts.append(f"  • {video_title}\n    Video ID: {video_id} ({status})")
                        response_parts.append(f"    Chunks: {indexed_segments}/{total_segments} indexed")
                        response_parts.append(f"    Chunk 1: {chunks_info[0]['video_id']} ({chunks_info[0]['time_range']})")
                        if result.get("remaining_segments_processing"):
                            response_parts.append(f"    ⏳ Remaining {total_segments - indexed_segments} chunk(s) processing in background")
                    else:
                        response_parts.append(f"  • {video_title}\n    Video ID: {video_id} ({status})")
                else:
                    response_parts.append(f"  • {video_title}\n    Video ID: {video_id} ({status})")
        
        if failed_results:
            response_parts.append(f"\n❌ Failed to index {len(failed_results)} video(s):")
            for result in failed_results:
                video_title = result["video"].get("title", "Unknown")
                error = result["error"]
                response_parts.append(f"  • {video_title}\n    Error: {error}")
        
        if indexed_results:
            response_parts.append("\n💡 You can now analyze these videos by asking questions about them!")
        
        state["messages"].append(AIMessage(content="\n".join(response_parts)))
        state["selected_videos"] = selected_videos
        
        return state
    
    def _analyze_video(self, state: AgentState) -> AgentState:
        user_query = state.get("user_query", "")
        conversation_context = state.get("conversation_context", {})
        
        video_id = conversation_context.get("video_id")
        
        if not video_id:
            extract_prompt = f"""Extract the video ID from this query: "{user_query}"

Look for:
- TwelveLabs video IDs (alphanumeric strings)
- YouTube URLs (extract video ID from watch?v=...)

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
        
        analysis_prompt = user_query
        if "analyze" in user_query.lower() or "what" in user_query.lower():
            pass
        else:
            analysis_prompt = f"Analyze this video: {user_query}"
        
        try:
            result = self.twelvelabs_service.analyze_video(video_id, analysis_prompt)
            state["analysis_result"] = result
            state["video_id"] = video_id
            state["messages"].append(AIMessage(content=f"Analysis result:\n{result}"))
        except Exception as e:
            state["messages"].append(AIMessage(content=f"Error analyzing video: {str(e)}"))
        
        return state
    
    def _route_after_classify(self, state: AgentState) -> str:
        intent = state.get("intent", "chat")
        if intent not in ["chat", "find_videos", "index", "analyze"]:
            intent = "chat"
        return intent
    
    def _respond(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "")
        user_query = state.get("user_query", "")
        messages = state.get("messages", [])
        
        if intent == "chat":
            system_prompt = """You are a helpful AI assistant that helps users with YouTube video operations.
You can:
1. Find and search for YouTube videos based on queries
2. Index videos so they can be analyzed later (user must confirm before indexing)
3. Analyze already indexed videos to answer questions about their content

Be friendly, concise, and helpful. Explain your capabilities clearly."""
            
            chat_messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query)
            ]
            
            response = self.llm.invoke(chat_messages)
            state["messages"].append(AIMessage(content=response.content))
        else:
            if not messages or not any(isinstance(m, AIMessage) for m in messages):
                state["messages"].append(AIMessage(content="I've processed your request."))
        
        return state
    
    def process_query(self, user_query: str, conversation_context: Optional[Dict] = None, status_callback=None) -> Dict:
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
        
        final_state = self.graph.invoke(initial_state)
        
        messages = final_state.get("messages", [])
        response_text = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                response_text = msg.content
                break
        
        result = {
            "response": response_text
        }
        
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
        
        try:
            if hasattr(self, '_current_status_callback'):
                delattr(self, '_current_status_callback')
        except Exception:
            pass
        
        return result
