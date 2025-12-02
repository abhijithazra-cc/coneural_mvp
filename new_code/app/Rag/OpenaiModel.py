from langchain_openai import ChatOpenAI
import os
from langchain_core.runnables import RunnablePassthrough,RunnableLambda
from langchain_core.prompts import PromptTemplate
# Initialize the OpenAI language model for response generation
from pydantic import BaseModel
from langchain_core.output_parsers import PydanticOutputParser
class OpenaiModel():
      def __init__(self):
            self.llm=ChatOpenAI(model_name="gpt-4.1", temperature=0,api_key=os.getenv('OPENAI_API_KEY'),streaming=False)
            self.prompt=None
            self.model_response=None
   
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
     • The answer must:
           - Explain the conflict
           - Mention which documents support each value
           - State which value is most recent *only if date_time metadata is available*
     • Do NOT invent any date_time or metadata.
     • Use citations directly inside the sentence:  
           (sources: file1.pdf, file2.pdf)

4. If the answer does NOT appear in the context:

     • Start with: "Not available in provided context."  
     • Then answer using your general knowledge.  
     • Use citation: ["model_knowledge"]

5. Do NOT hallucinate filenames or metadata.

=========================================
FINAL OUTPUT FORMAT (STRICT)
=========================================

You must ONLY return the following two fields:

{{
  "response": "<Single natural-language answer with inline citations> ",
  "citation": [json("file1.pdf","doc_id"), json("file2.pdf","doc_id"), ...]   // list of every file used
}}

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

# Create a PromptTemplate instance with the defined template and input variables
            self.prompt = PromptTemplate(
          template=PROMPT_TEMPLATE, input_variables=["context", "query"]
          )
            return self.prompt
      def get_llm(self):
            return self.llm
      

      def generate_answer_with_structure(self,context,query,schema:BaseModel):
            parser=PydanticOutputParser(pydantic_object=schema)
            chain=self.get_prompt_with_parser(parser=parser) | self.get_llm()
            # chain=self.get_prompt() | self.get_llm()

            result=chain.invoke({"context":context,"query":query})
            self.model_response=result
            return result





      def generate_answer(self,context,query):
            chain=self.get_prompt() | self.get_llm()
            # print(self.get_prompt())
            result=chain.invoke({"context":context,"query":query})
            self.model_response=result
            return result
            
      def get_prompt_with_parser(self,parser):
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


<context>
{context}
</context>
<question>
{query}
</question>


Assistant:"""

# Create a PromptTemplate instance with the defined template and input variables
            self.prompt = PromptTemplate(
          template=f"{PROMPT_TEMPLATE}{{format_instruction}}", input_variables=["context", "query"],
          partial_variables={'format_instruction':parser.get_format_instructions()}
          )
            return self.prompt
      
      def generate_answer_with_structure(self,context,query,schema:BaseModel):
            parser=PydanticOutputParser(pydantic_object=schema)
            chain=self.get_prompt_with_parser(parser=parser) | self.get_llm()
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
      def generate_stream_answer_with_structure(self,context,query,schema):
            import time
            parser=PydanticOutputParser(pydantic_object=schema)
            chain=self.get_prompt_with_parser(parser=parser) | self.get_llm()
            # chain=self.get_prompt() | self.get_llm()
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
