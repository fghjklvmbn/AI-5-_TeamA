import requests

from backend.configs.service_config import (
    ARCHIVE_HOST,
    ARCHIVE_PORT
)


class ArchiveService:

    @staticmethod
    def get_voice(
        voice_id
    ):
        response = requests.get(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/voice/{voice_id}"
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def create_voice(
        payload
    ):

        response = requests.post(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/voice",
            json=payload
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def get_voice_list():

        response = requests.get(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/voice/list"
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def create_session(
        session_name
    ):

        response = requests.post(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/session",
            json={
                "session_name":
                session_name
            }
        )

        return response.json()

    @staticmethod
    def get_session_list():

        response = requests.get(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/session/list"
        )

        return response.json()

    @staticmethod
    def get_history(
        session_id
    ):

        response = requests.get(
            f"http://{ARCHIVE_HOST}:{ARCHIVE_PORT}/conversation/history/{session_id}"
        )

        return response.json()