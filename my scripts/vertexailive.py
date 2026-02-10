import asyncio
from google import genai
from google.genai.types import (Content, HttpOptions, LiveConnectConfig,
                                Modality, Part)
from dotenv import load_dotenv

load_dotenv()


async def run():
    client = genai.Client(http_options=HttpOptions(api_version="v1beta1"))
    model_id = "gemini-2.0-flash-live-preview-04-09"

    async with client.aio.live.connect(
        model=model_id,
        config=LiveConnectConfig(response_modalities=[Modality.TEXT]),
    ) as session:
        text_input = "Hello? Gemini, are you there?"
        print("> ", text_input, "\n")
        await session.send_client_content(
            turns=Content(role="user", parts=[Part(text=text_input)])
        )

        response = []

        async for message in session.receive():
            if message.text:
                response.append(message.text)

        print("".join(response))


if __name__ == "__main__":
    asyncio.run(run())