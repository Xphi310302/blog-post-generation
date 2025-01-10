from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
import os
import dotenv

dotenv.load_dotenv()


def setup_openai_settings():
    Settings.llm = OpenAI(
        model="gpt-4o-mini", temperature=0.01, api_key=os.getenv("OPENAI_API_KEY")
    )
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")
    return Settings


_Settings = setup_openai_settings()
