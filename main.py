import streamlit as st
import os
import asyncio
import uuid
from agent import DocumentResearchAgent
from agent.event import ProgressEvent
import nest_asyncio

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

async def save_uploaded_files(uploaded_files, data_path):
    file_paths = []
    for uploaded_file in uploaded_files:
        file_path = os.path.join(data_path, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        file_paths.append(file_path)
    return file_paths

async def initialize_agent(file_paths):
    unique_id = str(uuid.uuid4())
    st.markdown(f"### Unique ID: {unique_id}")
    return DocumentResearchAgent(
        file_paths=file_paths,
        collection_name=f"document-{unique_id}",
        similarity_top_k=10,
        timeout=600,
        verbose=True,
    )

async def process_query(agent, query):
    handler = agent.run(query=query, tools=[agent.tool])
    progress_box = st.empty()
    
    async for ev in handler.stream_events():
        if isinstance(ev, ProgressEvent):
            progress_box.markdown(ev.progress)
    
    final_result = await handler
    st.markdown("### Final Result:")
    st.markdown(final_result)

def main():
    st.title("Blog Post Generator")
    
    data_path = "data"
    os.makedirs(data_path, exist_ok=True)
    
    uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)
    
    if "agent" not in st.session_state and uploaded_files:
        file_paths = asyncio.run(save_uploaded_files(uploaded_files, data_path))
        st.session_state.agent = asyncio.run(initialize_agent(file_paths))
        for file_path in file_paths:
            os.remove(file_path)
    
    query = st.text_input("Enter your query:", "Tell me about the budget of the San Francisco Police Department in 2023")
    
    if st.button("Run") and "agent" in st.session_state:
        asyncio.run(process_query(st.session_state.agent, query))

if __name__ == "__main__":
    main()