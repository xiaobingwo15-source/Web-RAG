from google import genai
from google.genai import types
from langfuse import observe, get_client
from app.config import Settings

RAG_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based on the provided documents. "
    "Only use information from the retrieved document context to answer questions. "
    "If the documents do not contain enough information to answer the question, "
    "say \"I don't have enough information in the uploaded documents to answer that question.\" "
    "Do not make up or infer information that is not explicitly stated in the documents. "
    "When referencing information, mention which document it came from if possible."
)


def get_gemini_client() -> genai.Client:
    settings = Settings()
    return genai.Client(api_key=settings.google_api_key)


def _build_config(
    file_search_store_name: str | None = None,
) -> types.GenerateContentConfig:
    if file_search_store_name:
        return types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=2048,
            tools=[
                types.Tool(
                    file_search=types.FileSearch(
                        file_search_store_names=[file_search_store_name]
                    )
                )
            ],
            system_instruction=RAG_SYSTEM_PROMPT,
        )
    return types.GenerateContentConfig(
        temperature=0.7,
        max_output_tokens=2048,
    )


@observe(name="gemini_chat", as_type="generation")
async def generate_chat_response(
    client: genai.Client,
    message: str,
    history: list[types.Content] | None = None,
    file_search_store_name: str | None = None,
) -> str:
    langfuse = get_client()
    langfuse.update_current_generation(
        model="gemini-2.5-flash",
        input={"message": message},
    )

    contents = history or []
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    ))

    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=_build_config(file_search_store_name),
    )

    langfuse.update_current_generation(output={"response": response.text})
    return response.text


@observe(name="gemini_chat_stream", as_type="generation")
async def generate_chat_response_stream(
    client: genai.Client,
    message: str,
    history: list[types.Content] | None = None,
    file_search_store_name: str | None = None,
):
    langfuse = get_client()
    langfuse.update_current_generation(
        model="gemini-2.5-flash",
        input={"message": message},
    )

    contents = history or []
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=message)],
    ))

    response_stream = await client.aio.models.generate_content_stream(
        model="gemini-2.5-flash",
        contents=contents,
        config=_build_config(file_search_store_name),
    )

    full_response = ""
    async for chunk in response_stream:
        if chunk.text:
            full_response += chunk.text
            yield chunk.text

    langfuse.update_current_generation(output={"response": full_response})
