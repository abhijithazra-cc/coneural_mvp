from langchain_openai import ChatOpenAI
import os
from langchain_core.runnables import RunnablePassthrough,RunnableLambda
from langchain_core.prompts import PromptTemplate
# Initialize the OpenAI language model for response generation

class OpenaiModel():
      def __init__(self):
            self.llm=ChatOpenAI(model_name="gpt-4o-mini", temperature=0,api_key=os.getenv('OPENAI_API_KEY'),streaming=True)
            self.prompt=None
            self.model_response=None

      def get_prompt(self):
            PROMPT_TEMPLATE = """
You are an enterprise RAG assistant specialized in answering questions based on the provided organization documents context.

FOLLOW STRICT RULES:

1. Always read the provided context carefully.  
2. If the answer is found in the context →  
      • Extract it exactly  
      • Never modify facts  
      • Provide a citation for each extracted part using this format:
            "citation": "documnent_id,filename"

3. If multiple context chunks contain different or conflicting information →  
      • Provide MULTIPLE answers  
      • Each with its own citation:
            "answer1": "content": "...", "citation": "..." 
            "answer2": "content": "...", "citation": "..." 

4. If context does NOT contain the answer →  
      • Respond using your own general knowledge  
      • Clearly mark the citation as:
            "citation": "model_knowledge"

5. Never hallucinate citations that don't exist.  
6. Final output must ALWAYS be valid JSON with this schema:

ANSWER FORMAT:
answer:... , citation: ...filename

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
      
      def generate_answer(self,context,query):
            chain=self.get_prompt() | self.get_llm()

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
