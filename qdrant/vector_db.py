import os
from qdrant_client import AsyncQdrantClient, QdrantClient
from llama_index.core import VectorStoreIndex, StorageContext, Settings
from llama_parse import LlamaParse
from llama_index.vector_stores.qdrant import QdrantVectorStore
from loguru import logger


class QdrantManager:
    def __init__(self):
        self.client = self.initialize_qdrant_client()
        self.async_client = self.initialize_async_qdrant_client()

    def initialize_qdrant_client(self):
        return QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )

    def initialize_async_qdrant_client(self):
        return AsyncQdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )

    def fetch_collection_names(self):
        collections = self.client.get_collections()
        return [collection.name for collection in collections.collections]

    def create_or_load_index(self, collection_name, file_paths):
        vector_store = QdrantVectorStore(
            client=self.client,
            aclient=self.async_client,
            collection_name=collection_name,
        )
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        collection_name_list = self.fetch_collection_names()
        if collection_name not in collection_name_list:
            logger.info(f"Create new collection {collection_name}")
            documents = []
            for file_path in file_paths:
                documents.extend(
                    LlamaParse(result_type="markdown").load_data(file_path)
                )
            return VectorStoreIndex.from_documents(
                documents=documents,
                storage_context=storage_context,
            )
        else:
            logger.info(f"Load collection {collection_name}")
            return VectorStoreIndex.from_vector_store(vector_store=vector_store)
