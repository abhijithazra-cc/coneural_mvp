from langchain_openai import ChatOpenAI
import os
from langchain_core.runnables import RunnablePassthrough,RunnableLambda
from langchain_core.prompts import PromptTemplate
# Initialize the OpenAI language model for response generation
from pydantic import BaseModel

class OpenaiModel():
      def __init__(self):
            self.llm=ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0,api_key=os.getenv('OPENAI_API_KEY'),streaming=True)
            self.prompt=None
            self.model_response=None
      def get_prompt(self):
            PROMPT_TEMPLATE = """
SYSTEM PROMPT:

You are a Retrieval-Augmented Generation (RAG) assistant.

You are provided with the following context chunks extracted from one or more documents.
Use ONLY this context to answer the user's question.

Your rules are:
1. **Do not generate or infer** any information not explicitly present in the provided context.
2. **If the context does not contain an answer**, reply exactly with:
   "The answer is not available in the provided context."
3. Never use prior knowledge or external facts.
4. Do not make assumptions, guesses, or creative elaborations.
5. When citing or explaining, refer only to what is in the chunks.
6. Maintain factual accuracy strictly bound to the given chunks.
7. Be concise and formal.
8. Answer should not look like gpt generated

The response should be specific and use statistics or numbers when possible.

IMPORTANT NOTE:

Always answer every user query in TWO different styles.

1) Response A — Short & Direct
   - 3 to 6 lines
   - Straight to the point
   - Actionable
   - No unnecessary explanation

2) Response B — Detailed & Expanded
   - Full explanation
   - Step-by-step reasoning
   - Examples
   - Best practices
   - Edge cases if relevant

RULES:
- Always output both Response A and Response B for every user query.
- Label them exactly as:
  "Response A (Short):"
  "Response B (Detailed):"
- Do NOT ask which one the user prefers. Always generate both.
- Both responses must answer the same question but with different depth.

OUTPUT FORMAT:

Response A (Short):
[short answer]

Response B (Detailed):
[detailed answer]

<context>
{context}
</context>

<question>
{query}
</question>

The response should be specific and use statistics or numbers when possible.

Assistant:"""

# Create a PromptTemplate instance with the defined template and input variables
            self.prompt = PromptTemplate(
          template=PROMPT_TEMPLATE, input_variables=["context", "query"]
          )
            return self.prompt
      def get_llm(self):
            return self.llm
      
      def generate_answer(self,context,query):
            chain=self.get_prompt() | self.get_llm()

            result=chain.invoke({"context":context,"query":query})
            self.model_response=result
            return result
      def generate_answer_with_structure(self,context,query,schema:BaseModel):
            chain=self.get_prompt() | self.get_llm().with_structured_output(schema=schema)
            # chain=self.get_prompt() | self.get_llm()

            result=chain.invoke({"context":context,"query":query})
            self.model_response=result
            return result
      def generate_stream_answer(self,context,query):
            import time
            chain=self.get_prompt() | self.get_llm()
            # chain=self.get_prompt() | RunnableLambda(lambda x: self.get_llm().stream(x))
            result=chain.stream({"context":context,"query":query})
            # result=chain.invoke({"context":context,"query":query})
            # for res in result:
            #       print(res.content,end="",flush=True)
            # self.model_response=result
            return result
      def set_model_response(self,docs):
            self.model_response=docs
      def get_model_response(self):
            return self.model_response
      
            


# Define the prompt template for generating AI responses
