import gradio as gr

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

    history = (
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

        history
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

    history = (
        load_history(
            session_id
        )
    )

    return (
        session_id,
        history
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

        return []

    conversations = (
        get_history(
            session_id
        )
    )

    messages = []

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

    return messages


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
            pipeline.run_text_with_tts(
                session_id,
                message,
                voice_id
            )
        )

    else:
        result = (
            send_chat(
                session_id,
                message
            )
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