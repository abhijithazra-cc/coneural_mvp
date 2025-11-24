from langchain_openai import ChatOpenAI
import os
from langchain_core.runnables import RunnablePassthrough,RunnableLambda
from langchain_core.prompts import PromptTemplate
# Initialize the OpenAI language model for response generation
from pydantic import BaseModel
from langchain_core.output_parsers import PydanticOutputParser
class OpenaiModel():
      def __init__(self):
            self.llm=ChatOpenAI(model_name="gpt-4.1", temperature=0,api_key=os.getenv('OPENAI_API_KEY'),streaming=True)
            self.prompt=None
            self.model_response=None
   
      def get_prompt(self):
            PROMPT_TEMPLATE = """
You are an enterprise RAG assistant specialized in answering questions based on the provided organization documents context.

FOLLOW STRICT RULES:

1. Always read the provided context carefully.  
2. If the answer is found in the context →  
      • Extract it exactly  
      • Provide a citation for each extracted part using this format:
            "citation": "filename"

3. If multiple context chunks contain different or conflicting information →  
      • Provide MULTIPLE answers  

      Example : pdf1 contain ww1 happend in 1940 , pdf2 say ww1 happend in 1942
                 so ANSWER FORMATE:  1. answer1:ww1 happend in 1940 , citation:pdf1, 2. answer2:ww2 happend in 1942 citation:pdf2
4. If context does NOT contain the answer →  
      • Respond using your own general knowledge  
      • Clearly mark the citation as:
            "citation": "model_knowledge"

5. Never hallucinate citations that don't exist.  


ANSWER FORMAT:

if multiple conflicting data ,remember filename across citation should be unique
answer1:... , citation1: ...filename1
answer2:... , citation2: ...filename2
if same answer in multiple document source , remember filename across citation should be unique
answer1..., citation1:...filename1, ...filename2
.
.
.


<context>
{context}
</context>
<question>
{query}
</question>


Assistant:"""

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
