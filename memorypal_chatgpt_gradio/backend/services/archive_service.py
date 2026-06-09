import requests


ARCHIVE_URL = (
    "http://localhost:8004"
)


class ArchiveService:

    @staticmethod
    def create_voice(
        payload
    ):

        response = requests.post(
            f"{ARCHIVE_URL}/voice",
            json=payload
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def get_voice_list():

        response = requests.get(
            f"{ARCHIVE_URL}/voice/list"
        )

        response.raise_for_status()

        return response.json()

    @staticmethod
    def get_voice(
        voice_id
    ):

        response = requests.get(
            f"{ARCHIVE_URL}/voice/{voice_id}"
        )

        response.raise_for_status()

        return response.json()