
import os
import time

from fastapi import APIRouter
from pydantic import BaseModel
from google import genai
from google.genai import types
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable


# ============================================================
# Config
# ============================================================

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL = "gemini-3.5-flash-lite"

router = APIRouter(prefix="/search", tags=["search"])


# ============================================================
# Request / Response models
# ============================================================

class SearchRequest(BaseModel):
    query: str
    num_results: int = 5


class GroundingSource(BaseModel):
    title: str | None = None
    url: str | None = None


class SearchResponse(BaseModel):
    query: str
    rewritten_query: str
    answer: str
    num_sources: int
    time_taken_ms: float
    sources: list[GroundingSource]


# ============================================================
# Query rewrite prompt
# ============================================================

REWRITE_PROMPT = """Rewrite the user's query below into a short, keyword-rich web
search query. Keep it factually equivalent, remove filler words, do NOT answer
the question, do NOT add quotes, do NOT explain. Output ONLY the rewritten
query on a single line.

User query: {query}
Rewritten query:"""


# ============================================================
# Query Rewriter
# ============================================================

class QueryRewriter:
    """
    Rewrites casual/natural-language user queries into
    keyword-rich search queries.
    """

    def __init__(self, api_key: str, model: str = MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def rewrite(self, query: str) -> str:
        """
        Synchronous query rewriting.
        """

        prompt = REWRITE_PROMPT.format(query=query)

        config = types.GenerateContentConfig(
            max_output_tokens=60,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            maximum_remote_calls=1,
                        ),
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            text = getattr(response, "text", None)

            if not text:
                return query

            rewritten = (
                text.strip()
                .strip('"')
                .splitlines()[0]
                .strip()
            )

            return rewritten if rewritten else query

        except Exception:
            # Fall back to original query if rewriting fails
            return query


# ============================================================
# Gemini Search Service
# ============================================================

class GeminiSearchService:
    """
    Synchronous Gemini Google Search grounding service.
    """

    def __init__(self, api_key: str, model: str = MODEL):
        self.client = genai.Client(api_key=api_key)
        self.model = model

        self.rewriter = QueryRewriter(
            api_key=api_key,
            model=model,
        )

    def search(self, query: str, num_results: int = 5) -> dict:
        """
        Perform a synchronous Gemini Google Search.
        """

        # Step 1: Rewrite query
        rewritten_query = self.rewriter.rewrite(query)

        # Step 2: Configure Google Search grounding
        config = types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ],
            max_output_tokens=400,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=5,
            ),
        )

        # Step 3: Execute synchronous Gemini request
        start = time.monotonic()

        response = self.client.models.generate_content(
            model=self.model,
            contents=rewritten_query,
            config=config,
        )

        elapsed_ms = (time.monotonic() - start) * 1000

        # Step 4: Extract answer
        answer_text = getattr(response, "text", None) or ""

        # Step 5: Extract grounding sources
        sources = []

        try:
            grounding = response.candidates[0].grounding_metadata

            chunks = grounding.grounding_chunks or []

            for chunk in chunks[:num_results]:
                web = getattr(chunk, "web", None)

                if web:
                    sources.append(
                        {
                            "title": getattr(web, "title", None),
                            "url": getattr(web, "uri", None),
                        }
                    )

        except (AttributeError, IndexError, TypeError):
            pass

        # Step 6: Return normalized response
        return {
            "query": query,
            "rewritten_query": rewritten_query,
            "answer": answer_text,
            "num_sources": len(sources),
            "time_taken_ms": round(elapsed_ms),
            "sources": sources,
        }


# ============================================================
# Instantiate service once
# ============================================================

search_service = GeminiSearchService(
    api_key=GEMINI_API_KEY
)


# ============================================================
# LangChain Tool
# ============================================================

@tool
def gemini_search_tool(
    query: str,
    num_results: int = 5,
) -> dict:
    """
    Search the web using Gemini's native Google Search grounding.

    Automatically rewrites the query into keyword-rich form
    before searching.

    Returns an answer string plus the grounding sources used.
    """

    return search_service.search(
        query=query,
        num_results=num_results,
    )


# ============================================================
# Reusable Search Node
# ============================================================

class GeminiSearchNode:
    """
    Reusable synchronous web search node using Gemini's
    native Google Search capability.

    The tool can be bound to a LangChain LLM and the search
    method can also be called directly.
    """

    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            temperature=0.1,
            google_api_key=GEMINI_API_KEY,
            streaming=False,
        )

        self.tools = [gemini_search_tool]

        self.llm_with_tools = self.llm.bind_tools(
            self.tools
        )

    @traceable(
        name="web_search",
        project="core",
        metadata={
            "description": (
                "Perform web search using Gemini's "
                "Google Search capability"
            )
        },
        tags=["search", "gemini"],
    )
    def search(
        self,
        query: str,
        num_results: int = 5,
    ) -> dict:

        res = gemini_search_tool.invoke(query)
        # res = self.llm_with_tools.invoke(query)

        print("web_search", res)

        return res


    # def search(
    #     self,
    #     query: str,
    #     num_results: int = 5,
    # ) -> dict:

    #     ai_msg = self.llm_with_tools.invoke(query)

    #     print("web_search", ai_msg)

    #     if not ai_msg.tool_calls:
    #         return {"answer": ai_msg.content, "sources": []}

    #     tool_call = ai_msg.tool_calls[0]

    #     result = gemini_search_tool.invoke(tool_call["args"])
 
    #     return result



# class GeminiSearchNode:
#     """
#     Reusable web search node using Gemini's native Google Search capability.
#     Provides search results that can be used by other LLM providers (OpenAI, Anthropic).
#     """

#     def __init__(self):
#         self.llm = ChatGoogleGenerativeAI(
#             model="gemini-3.5-flash",
#             temperature=0.1,
            
#             google_api_key=os.getenv("GOOGLE_API_KEY"),
#             streaming=True,
#         )
#     @traceable(name="web_search", project="core", metadata={"description": "Perform web search using Gemini's Google Search capability"}, tags=["search","gemini"])
#     def search(self, query: str, num_results: int = 5) -> str:
#         """
#         Perform web search using Gemini's Google Search capability.

#         Args:
#             query: The search query string
#             num_results: Number of results to return (default 5)

#         Returns:
#             String containing formatted search results
#         """
#         if not query or not query.strip():
#             return ""

#         print(f"🔍 GEMINI GOOGLE SEARCH INVOKED: query='{query}'")
#         search_prompt = f"""Search the web for information about: {query}"""
# #         search_prompt=f"""Rewrite the user's query below into a short, keyword-rich web search query.Search the web for information about. Keep it factually equivalent

# # User query: {query}
# #"""

#         try:
#             response = self.llm.bind(tools=[{"google_search": {}}]).invoke(search_prompt)
#             print("web_search_result",response)
#             search_results = response.content if hasattr(response, 'content') else str(response)
#             print(f"✅ GEMINI GOOGLE SEARCH SUCCESSFUL: received {len(search_results)} characters")
#             return search_results
#         except Exception as e:
#             print(f"❌ GEMINI GOOGLE SEARCH ERROR: {e}")
#             return ""
