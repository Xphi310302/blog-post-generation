from typing import List
from llama_index.core.workflow import (
    step,
    Context,
    StartEvent,
    StopEvent,
    Workflow,
)
from llama_index.core.agent import FunctionCallingAgent
from config import _Settings
from qdrant.vector_db import QdrantManager
from llama_index.core.tools import QueryEngineTool
from agent.event import (
    OutlineEvent,
    QuestionEvent,
    AnswerEvent,
    ReviewEvent,
    ProgressEvent,
)


class DocumentResearchAgent(Workflow):
    def __init__(
        self,
        file_paths=None,
        similarity_top_k=10,
        collection_name="documents",
        *args,
        **kwargs,
    ):
        super().__init__(
            *args, **kwargs
        )  # Initialize parent class with all args and kwargs
        self.file_paths = file_paths if file_paths is not None else []
        self.similarity_top_k = similarity_top_k
        self.collection_name = collection_name
        self.Settings = _Settings

        index = QdrantManager().create_or_load_index(
            collection_name=self.collection_name, file_paths=self.file_paths
        )
        query_engine = index.as_query_engine(similarity_top_k=self.similarity_top_k)
        self.tool = QueryEngineTool.from_defaults(
            query_engine,
            name="document_retrieval_tool",
            description=f"A RAG engine with extremely detailed information about the {str(self.file_paths)}",
        )

    # get the initial request and create an outline of the blog post knowing nothing about the topic
    @step()
    async def formulate_plan(self, ctx: Context, ev: StartEvent) -> OutlineEvent:
        query = ev.query
        await ctx.set("original_query", query)
        await ctx.set("tools", ev.tools)

        prompt = f"""You are an expert at writing blog posts. You have been given a topic to write
        a blog post about. Plan an outline for the blog post; it should be detailed and specific.
        Another agent will formulate questions to find the facts necessary to fulfill the outline.
        The topic is: {query}"""

        response = await self.Settings.llm.acomplete(prompt)

        ctx.write_event_to_stream(ProgressEvent(progress="Outline:\n" + str(response)))

        return OutlineEvent(outline=str(response))

    # formulate some questions based on the outline
    @step()
    async def formulate_questions(
        self, ctx: Context, ev: OutlineEvent
    ) -> QuestionEvent:
        outline = ev.outline
        await ctx.set("outline", outline)

        prompt = f"""You are an expert at formulating research questions. You have been given an outline
        for a blog post. Formulate a series of simple questions that will get you the facts necessary
        to fulfill the outline. You cannot assume any existing knowledge; you must ask at least one
        question for every bullet point in the outline. Avoid complex or multi-part questions; break
        them down into a series of simple questions. Your output should be a list of questions, each
        on a new line. Do not include headers or categories or any preamble or explanation; just a
        list of questions. For speed of response, limit yourself to 8 questions. The outline is: {outline}"""

        response = await self.Settings.llm.acomplete(prompt)

        questions = str(response).split("\n")
        questions = [x for x in questions if x]

        ctx.write_event_to_stream(
            ProgressEvent(progress="Formulated questions:\n" + "\n".join(questions))
        )

        await ctx.set("num_questions", len(questions))

        ctx.write_event_to_stream(
            ProgressEvent(progress="Questions:\n" + "\n".join(questions))
        )

        for question in questions:
            ctx.send_event(QuestionEvent(question=question))

    # answer each question in turn
    @step()
    async def answer_question(self, ctx: Context, ev: QuestionEvent) -> AnswerEvent:
        question = ev.question
        if not question or question.isspace() or question == "" or question is None:
            ctx.write_event_to_stream(
                ProgressEvent(progress=f"Skipping empty question.")
            )  # Log skipping empty question
            return None
        agent = FunctionCallingAgent.from_tools(
            await ctx.get("tools"),
            verbose=True,
        )
        response = await agent.aquery(question)

        ctx.write_event_to_stream(
            ProgressEvent(
                progress=f"To question '{question}' the agent answered: {response}"
            )
        )

        return AnswerEvent(question=question, answer=str(response))

    # given all the answers to all the questions and the outline, write the blog poost
    @step()
    async def write_report(self, ctx: Context, ev: AnswerEvent) -> ReviewEvent:
        # wait until we receive as many answers as there are questions
        num_questions = await ctx.get("num_questions")
        results = ctx.collect_events(ev, [AnswerEvent] * num_questions)
        if results is None:
            return None

        # maintain a list of all questions and answers no matter how many times this step is called
        try:
            previous_questions = await ctx.get("previous_questions")
        except:
            previous_questions = []
        previous_questions.extend(results)
        await ctx.set("previous_questions", previous_questions)

        prompt = f"""You are an expert at writing blog posts. You are given an outline of a blog post
        and a series of questions and answers that should provide all the data you need to write the
        blog post. Compose the blog post according to the outline, using only the data given in the
        answers. The outline is in <outline> and the questions and answers are in <questions> and
        <answers>.
        <outline>{await ctx.get("outline")}</outline>"""

        for result in previous_questions:
            prompt += f"<question>{result.question}</question>\n<answer>{result.answer}</answer>\n"

        ctx.write_event_to_stream(
            ProgressEvent(progress="Writing report with prompt:\n" + prompt)
        )

        report = await self.Settings.llm.acomplete(prompt)

        return ReviewEvent(report=str(report))

    # review the report. If it still needs work, formulate some more questions.
    @step
    async def review_report(
        self, ctx: Context, ev: ReviewEvent
    ) -> StopEvent | QuestionEvent:
        # we re-review a maximum of 3 times
        try:
            num_reviews = await ctx.get("num_reviews")
        except:
            num_reviews = 1
        num_reviews += 1
        await ctx.set("num_reviews", num_reviews)

        report = ev.report

        prompt = f"""You are an expert reviewer of blog posts. You are given an original query,
        and a blog post that was written to satisfy that query. Review the blog post and determine
        if it adequately answers the query and contains enough detail. If it doesn't, come up with
        a set of questions that will get you the facts necessary to expand the blog post. Another
        agent will answer those questions. Your response should just be a list of questions, one
        per line, without any preamble or explanation. For speed, generate a maximum of 4 questions.
        The original query is: '{await ctx.get("original_query")}'.
        The blog post is: <blogpost>{report}</blogpost>.
        If the blog post is fine, return just the string 'OKAY'."""

        response = await self.Settings.llm.acomplete(prompt)

        if response == "OKAY" or await ctx.get("num_reviews") >= 3:
            ctx.write_event_to_stream(ProgressEvent(progress="Blog post is fine"))
            return StopEvent(result=report)
        else:
            questions = str(response).split("\n")
            await ctx.set("num_questions", len(questions))
            ctx.write_event_to_stream(
                ProgressEvent(progress="Formulated some more questions")
            )
            for question in questions:
                ctx.send_event(QuestionEvent(question=question))
