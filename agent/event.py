from llama_index.core.workflow import Event


class OutlineEvent(Event):
    outline: str


class QuestionEvent(Event):
    question: str


class AnswerEvent(Event):
    question: str
    answer: str


class ReviewEvent(Event):
    report: str


class ProgressEvent(Event):
    progress: str
