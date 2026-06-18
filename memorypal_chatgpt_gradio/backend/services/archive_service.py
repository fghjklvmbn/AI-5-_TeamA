import requests

from backend.configs.service_config import ARCHIVE_HOST

class ArchiveService:

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
    def get_voice(
        voice_id
    ):

        response = requests.get(
            f"{ARCHIVE_HOST}/voice/{voice_id}"
        )

        response.raise_for_status()

        return response.json()