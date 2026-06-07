from backend.pipeline.clients.archive_client import (
    ArchiveClient
)

archive_client = ArchiveClient(
    "localhost",
    8004
)


def create_session():

    session = (
        archive_client.create_session(
            "새 채팅"
        )
    )

    return session["id"]


def get_session_list():

    return (
        archive_client.get_session_list()
    )


def get_history(
    session_id
):

    return (
        archive_client.get_history(
            session_id
        )
    )


def create_default_session():

    sessions = (
        get_session_list()
    )

    if len(sessions) > 0:

        return sessions[0]["id"]

    return create_session()