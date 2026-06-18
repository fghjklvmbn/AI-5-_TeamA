import requests

from backend.configs.service_config import (
    ARCHIVE_HOST
)


class ArchiveService:

    @staticmethod
    def get_voice(
        voice_id
    ):
        response = requests.get(
            f"{ARCHIVE_HOST}/voice/{voice_id}"
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def create_voice(
        payload
    ):

        response = requests.post(
            f"{ARCHIVE_HOST}/voice",
            json=payload
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def get_voice_list():

        response = requests.get(
            f"{ARCHIVE_HOST}/voice/list"
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def create_session(
        session_name
    ):

        response = requests.post(
            f"{ARCHIVE_HOST}/session",
            json={
                "session_name":
                session_name
            }
        )

        return response.json()

    @staticmethod
    def get_session_list():

        response = requests.get(
            f"{ARCHIVE_HOST}/session/list"
        )

        return response.json()

    @staticmethod
    def get_history(
        session_id
    ):

        response = requests.get(
            f"{ARCHIVE_HOST}/conversation/history/{session_id}"
        )

        return response.json()
    
    @staticmethod
    def upload_audio(
        audio_path
    ):
        print(audio_path)
        with open(
            audio_path,
            "rb"
        ) as f:

            response = requests.post(
                f"{ARCHIVE_HOST}/upload/audio",
                files={
                    "file": f
                }
            )
        print(response.json)

        return response.json()