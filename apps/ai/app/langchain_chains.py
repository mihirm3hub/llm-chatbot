from __future__ import annotations

from datetime import datetime
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from .langchain_runtime import get_chat_model, safe_json


class SlotExtraction(BaseModel):
    intent: Literal["booking", "inquiry", "reschedule"] | None = Field(default=None)
    date: str | None = Field(default=None, description="YYYY-MM-DD")
    time: str | None = Field(default=None, description="HH:MM 24-hour")
    timezone: str | None = Field(default=None, description="IANA timezone or UTC")
    service_type: str | None = Field(default=None)


def to_langchain_messages(messages: list[dict]) -> list:
    out: list = []
    for m in messages or []:
        role = (m.get("role") or "").lower()
        content = m.get("content")
        if not isinstance(content, str):
            continue
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


def extract_slots(*, message: str, existing_slots: dict) -> dict:
    parser = PydanticOutputParser(pydantic_object=SlotExtraction)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You extract intent + appointment booking slots from ONE user message. "
                "Output must follow the schema exactly. If you are uncertain, use null. "
                "Do NOT invent a date/time/timezone. "
                "Intent must be one of: booking, inquiry, reschedule.\n\n{format_instructions}",
            ),
            (
                "human",
                "Message: {message}\nExisting slots: {existing_slots}",
            ),
        ]
    ).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | get_chat_model(temperature=0) | parser
    parsed: SlotExtraction = chain.invoke(
        {"message": message, "existing_slots": safe_json(existing_slots or {})}
    )
    data = parsed.model_dump()
    return {
        "intent": data.get("intent"),
        "date": data.get("date"),
        "time": data.get("time"),
        "timezone": data.get("timezone"),
        "service_type": data.get("service_type"),
    }


def compose_reply(*, history: list[dict], action: str, context: dict) -> str:
    """Use LangChain as the primary response composer.

    The Python code decides the action (business logic). The LLM writes the user-facing text.
    """

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful, conversational appointment booking assistant for a generic business. "
                "You respond naturally to ANY user message (including greetings or unrelated questions), "
                "but your primary goal is to help book/reschedule/cancel appointments. "
                "You must follow the requested ACTION and use CONTEXT. "
                "Rules: be concise; ask at most one question at a time when collecting booking details; "
                "do not invent a final date/time if missing; when proposing alternatives, list up to two. "
                "If the user asks something unrelated, answer briefly and then smoothly steer back to booking help."
                "\n\nACTION meanings:"
                "\n- ask_date: request a date"
                "\n- ask_time: request a time"
                "\n- not_booking: respond conversationally and ask for date/time to book"
                "\n- general_chat: respond conversationally to the user's message and offer booking help"
                "\n- cancelled: confirm cancellation"
                "\n- booked: confirm the booking"
                "\n- conflict: say slot is booked and propose alternatives"
                "\n- view_booking: summarize the latest booking or say none exists"
                "\n- invalid_datetime: ask for date+time again"
                "\n- outside_rules: explain business-hours rule"
            ),
            MessagesPlaceholder("history"),
            (
                "human",
                "ACTION: {action}\nCONTEXT_JSON: {context_json}\nWrite the assistant reply.",
            ),
        ]
    )

    chain = prompt | get_chat_model(temperature=0.2) | StrOutputParser()
    return (chain.invoke({
        "history": to_langchain_messages(history),
        "action": action,
        "context_json": safe_json(context or {}),
    }) or "").strip()
