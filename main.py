import streamlit as st
import os
from agent import DocumentResearchAgent
from agent.event import ProgressEvent
import asyncio
import uuid

# Streamlit file uploader for multiple PDF files
uploaded_files = st.file_uploader(
    "Upload PDF files", type=["pdf"], accept_multiple_files=True
)
data_path = "data"
if not os.path.exists(data_path):
    os.makedirs(data_path)

# Initialize agent only once per session
if "agent" not in st.session_state:
    if uploaded_files:
        # Save uploaded files temporarily
        file_paths = []
        for uploaded_file in uploaded_files:
            file_path = f"{data_path}/{uploaded_file.name}"
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            file_paths.append(file_path)

        # Generate a UUID v4
        unique_id = str(uuid.uuid4())
        st.markdown(f"### Unique ID: {unique_id}")
        st.session_state.agent = DocumentResearchAgent(
            file_paths=file_paths,
            collection_name=f"document-{unique_id}",
            similarity_top_k=10,
            timeout=600,
            verbose=True,
        )

        # Close after indexing
        for file_path in file_paths:
            os.remove(file_path)
query = st.text_input(
    "Enter your query:",
    "Tell me about the budget of the San Francisco Police Department in 2023",
)


async def run_query():
    handler = st.session_state.agent.run(  # Remove await here
        query=query,
        tools=[st.session_state.agent.tool],
    )

    # Display progress in a chat box
    progress_box = st.empty()

    async def handle_query_progress_and_result():
        async for ev in handler.stream_events():
            if isinstance(ev, ProgressEvent):
                progress_box.markdown(ev.progress)

        final_result = await handler  # Await the handler here
        # Display final result in a new box
        st.markdown("### Final Result:")
        st.markdown(final_result)

    # Run the combined function
    task = asyncio.create_task(handle_query_progress_and_result())
    await task


if st.button("Run"):
    asyncio.run(run_query())
