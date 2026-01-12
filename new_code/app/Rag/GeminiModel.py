import os
from pydantic import BaseModel

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnableLambda


class GeminiFlashModel:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=1,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            streaming=False,
        )
        self.prompt = None
        self.model_response = None

    # ---------------- PROMPT ---------------- #

    def get_prompt(self):
        PROMPT_TEMPLATE = """
You are an enterprise-grade RAG Assistant optimized for factual, citation-based answers.

=========================================
CORE RULES
=========================================

1. Always read the provided context carefully before answering.

2. If the context contains the answer:
     • Extract the exact values from the documents.
     • Never rewrite or modify factual numbers.
     • If multiple documents contain the same answer, treat them as supporting that answer.
     • If different documents give different answers, treat them as conflicting facts.

3. When conflicting information exists:
     • Write ONE combined narrative answer.
     • Explain the conflict
     • Mention which documents support each value
     • State which value is most recent only if date_time metadata is available
     • Do NOT invent any date_time or metadata.
     • Use citations inline: (sources: file1.pdf, file2.pdf)

4. If the answer does NOT appear in the context:
     • Start with: "Not available in provided context."
     • Then answer using general knowledge.
     • Use citation: ["model_knowledge"]

5. Do NOT hallucinate filenames or metadata.

=========================================
FINAL OUTPUT FORMAT (STRICT)
=========================================

{
  "response": "<Single natural-language answer with inline citations converted into HTML-tag list>",
  "citation": [["file1.pdf","document_id"]],
  "is_context_availale": "True" or "False"
}

=========================================
INPUT
=========================================

<context>
{context}
</context>

<question>
{query}
</question>

Assistant:
"""
        self.prompt = PromptTemplate(
            template=PROMPT_TEMPLATE,
            input_variables=["context", "query"],
        )
        return self.prompt

    def get_llm(self):
        return self.llm

    # ---------------- STRUCTURED OUTPUT ---------------- #

    def get_prompt_with_parser(self, parser):
        PROMPT_TEMPLATE = """
You are an enterprise-grade RAG Assistant optimized for factual, citation-based answers.

<context>
{context}
</context>

<question>
{query}
</question>

Assistant:
"""
        self.prompt = PromptTemplate(
            template=f"{PROMPT_TEMPLATE}{{format_instruction}}",
            input_variables=["context", "query"],
            partial_variables={
                "format_instruction": parser.get_format_instructions()
            },
        )
        return self.prompt

    def generate_answer_with_structure(self, context, query, schema: BaseModel):
        parser = PydanticOutputParser(pydantic_object=schema)
        chain = self.get_prompt_with_parser(parser) | self.get_llm()
        result = chain.invoke({"context": context, "query": query})
        self.model_response = result
        return result

    # ---------------- NORMAL RESPONSE ---------------- #

    def generate_answer(self, context, query):
        chain = self.get_prompt() | self.get_llm()
        result = chain.invoke({"context": context, "query": query})
        self.model_response = result
        return result

    # ---------------- STREAMING ---------------- #

    def generate_stream_answer(self, context, query):
        self.llm.streaming = True
        chain = self.get_prompt() | self.get_llm()
        return chain.stream({"context": context, "query": query})

    def generate_stream_answer_with_structure(self, context, query, schema):
        self.llm.streaming = True
        parser = PydanticOutputParser(pydantic_object=schema)
        chain = self.get_prompt_with_parser(parser) | self.get_llm()
        return chain.stream({"context": context, "query": query})

    # ---------------- STATE ---------------- #

    def set_model_response(self, docs):
        self.model_response = docs

    def get_model_response(self):
        return self.model_response
