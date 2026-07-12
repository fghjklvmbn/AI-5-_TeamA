import gradio as gr
import uuid
import requests

from backend.api.session_api import (
    create_session,
    get_session_list,
    get_history
)

from backend.api.chat_api import (
    send_message as send_chat
)

from backend.api.session_api import (
    create_default_session
)

from backend.api.chat_api import (
    pipeline
)



def initialize_chat():

    session_id = (
        create_default_session()
    )

    sessions = (
        get_session_list()
    )

    history, audio_path = (
        load_history(
            session_id
        )
    )

    return (
        session_id,

        gr.update(
            choices=[
                (
                    item["session_name"],
                    item["id"]
                )
                for item in sessions
            ],
            value=session_id
        ),

        history,
        audio_path
    )


def create_new_session():

    session_id = (
        create_session()
    )

    sessions = (
        get_session_list()
    )

    return (
        session_id,

        gr.update(
            choices=[
                (
                    item["session_name"],
                    item["id"]
                )
                for item in sessions
            ],
            value=session_id
        ),

        []
    )

def select_session(
    session_id
):

    history, audio_url = (
        load_history(
            session_id
        )
    )

    local_audio = None

    if audio_url:

        local_audio = (
            f"storage/history/history_{uuid.uuid4()}.wav"
        )

        response = (
            requests.get(
                audio_url
            )
        )

        with open(
            local_audio,
            "wb"
        ) as f:

            f.write(
                response.content
            )

    return (
        session_id,
        history,
        local_audio,
    )


def create_new_session_and_refresh():

    session_id = (
        create_session()
    )

    sessions = (
        get_session_list()
    )

    return (
        session_id,

        gr.update(
            choices=[
                (
                    item["session_name"],
                    item["id"]
                )
                for item in sessions
            ],
            value=session_id
        )
    )


def load_session_list():

    sessions = (
        get_session_list()
    )

    return gr.update(
        choices=[
            (
                item["session_name"],
                item["id"]
            )
            for item in sessions
        ]
    )


def load_history(
    session_id
):

    if not session_id:
        return [], None

    conversations = (
        get_history(
            session_id
        )
    )

    messages = []

    last_audio = None

    for item in conversations:

        messages.append(
            {
                "role": "user",
                "content":
                item["user_text"]
            }
        )

        messages.append(
            {
                "role": "assistant",
                "content":
                item["assistant_text"]
            }
        )

        if item.get(
            "output_audio_path"
        ):

            last_audio = (
                item["output_audio_path"]
            )

    return (
        messages,
        last_audio
    )


def send_message(
    message,
    history,
    session_id,
    voice_id
):

    if not message:

        return (
            history,
            ""
        )
    
    if not session_id:
        session_id = (
            create_default_session()
        )

    if voice_id:
        result = (
            pipeline.run(
                session_id=session_id,
                message=message,
                voice_id=voice_id
            )
        )
    else:
        raise ValueError("음성이 입력되지 않았습니다. 다시시도해주세요")
    
    # 오디오
    audio_url = (
        result["audio"]
    )
    

    local_audio = (
        f"storage/history/temp_{uuid.uuid4()}.wav"
    )

    response = requests.get(
        audio_url
    )

    with open(
        local_audio,
        "wb"
    ) as f:

        f.write(
            response.content
        )

    history.append(
        {
            "role": "user",
            "content": message
        }
    )

    history.append(
        {
            "role": "assistant",
            "content": result["text"]
        }
    )

    return (
        history,
        ""
    )