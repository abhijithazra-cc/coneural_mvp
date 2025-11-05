from langchain_openai import ChatOpenAI
import os
from langchain_core.prompts import PromptTemplate
# Initialize the OpenAI language model for response generation

class OpenaiModel():
      def __init__(self):
            self.llm=ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0,api_key=os.getenv('OPENAI_API_KEY'))
            self.prompt=None
      def get_prompt(self):
            PROMPT_TEMPLATE = """
Human: You are an AI assistant, and provides answers to questions by using fact based and statistical information when possible.
Use the following pieces of information to provide a concise answer to the question enclosed in <question> tags.
If you don't know the answer, just say that you don't know, don't try to make up an answer.
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
            return result
            
            


# Define the prompt template for generating AI responses
