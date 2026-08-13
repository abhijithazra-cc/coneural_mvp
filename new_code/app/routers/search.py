# import time
# import httpx
# from fastapi import FastAPI, HTTPException,APIRouter
# from pydantic import BaseModel
# from google import genai
# from google.genai import types
# # app = FastAPI(title="Search Speed Tester")
# router = APIRouter(prefix="/search", tags=["search"])
# # ---- Config ----
# import os
# GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")  # Gemini's Google Search API key
# MODEL = "gemini-3.5-flash-lite"  # fastest tier for grounded search


# # ---- Request/Response models ----
# class SearchRequest(BaseModel):
#     query: str
#     num_results: int = 5  # caps how many grounding sources we keep


# class GroundingSource(BaseModel):
#     title: str | None = None
#     url: str | None = None


# class SearchResponse(BaseModel):
#     query: str
#     answer: str
#     num_sources: int
#     time_taken_ms: float
#     sources: list[GroundingSource]


# # ---- Search service class ----
# class GeminiSearchService:
#     def __init__(self, api_key: str, model: str = MODEL):
#         self.client = genai.Client(api_key=api_key,)
#         self.model = model

#     async def search(self, query: str, num_results: int = 5) -> dict:
#         config = types.GenerateContentConfig(
#             tools=[types.Tool(google_search=types.GoogleSearch())],
#             max_output_tokens=400,  # keep low = faster generation
#             automatic_function_calling=types.AutomaticFunctionCallingConfig(
#         maximum_remote_calls=1,  # limit how many tool-call round trips Gemini can make
#     ),
#         )

#         start = time.monotonic()
#         response = await self.client.aio.models.generate_content(
#             model=self.model,
#             contents=query,
#             config=config,

#         )
#         elapsed_ms = time.monotonic() - start

#         # Extract grounding sources (search results Gemini actually used)
#         sources = []
#         try:
#             grounding = response.candidates[0].grounding_metadata
#             chunks = grounding.grounding_chunks or []
#             for chunk in chunks[:num_results]:
#                 web = getattr(chunk, "web", None)
#                 if web:
#                     sources.append({"title": web.title, "url": web.uri})
#         except (AttributeError, IndexError):
#             pass  # no grounding metadata returned

#         return {
#             "query": query,
#             "answer": response.text,
#             "num_sources": len(sources),
#             "time_taken_ms": round(elapsed_ms),
#             "sources": sources,
#         }


# # ---- Instantiate service once ----
# search_service = GeminiSearchService(api_key=GEMINI_API_KEY)


# # ---- Endpoint ----
# @router.post("/search", response_model=SearchResponse)
# async def search(req: SearchRequest):
#     if not req.query.strip():
#         raise HTTPException(status_code=400, detail="Query cannot be empty")
#     try:
#         return await search_service.search(req.query, req.num_results)
#     except Exception as e:
#         raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")



import os
import time
from fastapi import HTTPException, APIRouter
from pydantic import BaseModel
from google import genai
from google.genai import types
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

# ---- Config ----
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = "gemini-3.5-flash-lite"

router = APIRouter(prefix="/search", tags=["search"])


# ---- Request/Response models ----
class SearchRequest(BaseModel):
    query: str
    num_results: int = 5


class GroundingSource(BaseModel):
    title: str | None = None
    url: str | None = None


class SearchResponse(BaseModel):
    query: str            # original user query
    rewritten_query: str  # keyword-rich version actually searched
    answer: str
    num_sources: int
    time_taken_ms: float
    sources: list[GroundingSource]


# ---- Dedicated rewrite prompt (small & focused on ONE job) ----
REWRITE_PROMPT = """Rewrite the user's query below into a short, keyword-rich web
search query. Keep it factually equivalent, remove filler words, do NOT answer
the question, do NOT add quotes, do NOT explain. Output ONLY the rewritten
query on a single line.

User query: {query}
Rewritten query:"""


# ---- Query rewriter ----
class QueryRewriter:
    """Rewrites casual/natural-language user queries into keyword-rich search queries."""

    def __init__(self, api_key: str, model: str = MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def rewrite(self, query: str) -> str:
        prompt = REWRITE_PROMPT.format(query=query)
        config = types.GenerateContentConfig(
            max_output_tokens=60,
            temperature=0,
        )
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            text = getattr(response, "text", None)
            if not text:
                return query
            rewritten = text.strip().strip('"').splitlines()[0].strip()
            return rewritten if rewritten else query
        except Exception:
            return query  # fall back to original on failure


# ---- Search service class ----
class GeminiSearchService:
    def __init__(self, api_key: str, model: str = MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.rewriter = QueryRewriter(api_key=api_key, model=model)

    async def search(self, query: str, num_results: int = 5) -> dict:
        rewritten_query = await self.rewriter.rewrite(query)

        config = types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=400,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=1,
            ),
        )

        start = time.monotonic()
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=rewritten_query,
            config=config,
        )
        elapsed_ms = (time.monotonic() - start) * 1000  # was missing *1000 -> ms

        answer_text = getattr(response, "text", None) or ""

        sources = []
        try:
            grounding = response.candidates[0].grounding_metadata
            chunks = grounding.grounding_chunks or []
            for chunk in chunks[:num_results]:
                web = getattr(chunk, "web", None)
                if web:
                    sources.append({"title": web.title, "url": web.uri})
        except (AttributeError, IndexError, TypeError):
            pass

        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "answer": answer_text,
            "num_sources": len(sources),
            "time_taken_ms": round(elapsed_ms),
            "sources": sources,
        }


# ---- Instantiate service once ----
search_service = GeminiSearchService(api_key=GEMINI_API_KEY)


# ---- Tool wrapper (bindable to any LangChain LLM) ----
@tool
async def gemini_search_tool(query: str, num_results: int = 5) -> dict:
    """Search the web using Gemini's native Google Search grounding.
    Automatically rewrites the query into keyword-rich form before searching.
    Returns an answer string plus the grounding sources used."""
    return await search_service.search(query, num_results)


# ---- Reusable node that binds the tool ----
class GeminiSearchNode:
    """
    Reusable web search node using Gemini's native Google Search capability.
    Provides search results that can be used by other LLM providers (OpenAI, Anthropic).
    """

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            temperature=0.1,
            google_api_key=GEMINI_API_KEY,
            streaming=True,
        )
        self.tools = [gemini_search_tool]
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    async def search(self, query: str, num_results: int = 5) -> dict:
        return await gemini_search_tool.ainvoke({"query": query, "num_results": num_results})


# ---- Endpoint ----
search_node = GeminiSearchNode()


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    try:
        return await search_node.search(req.query, req.num_results)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")