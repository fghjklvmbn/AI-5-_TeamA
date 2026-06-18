import requests


class ArchiveClient:

    def __init__(
        self,
        host: str
    ):

        self.base_url = (
            f"{host}"
        )

    def create_session(
        self,
        session_name: str
    ):

        response = requests.post(

            f"{self.base_url}/session",

            json={
                "session_name":
                session_name
            }

        )

        return response.json()

    # 수정
    def save_conversation(
        self,
        payload
    ):

        response = requests.post(
            f"{self.base_url}/conversation",
            json=payload
        )

        return response.json()

    def get_session_list(
        self
    ):

        response = requests.get(
            f"{self.base_url}/session/list"
        )

        return response.json()


    def get_history(
        self,
        session_id
    ):

        response = requests.get(
            f"{self.base_url}/conversation/history/{session_id}"
        )

        return response.json()

    def create_voice(
        self,
        payload
    ):

        response = requests.post(
            f"{self.base_url}/voice",
            json=payload
        )

        return response.json()
    
    def get_voice(
        self,
        voice_id
    ):

        response = requests.get(
            f"{self.base_url}/voice/{voice_id}"
        )

        response.raise_for_status()

        return response.json()
    
    def get_voice_list(
        self
    ):

        response = requests.get(
            f"{self.base_url}/voice/list"
        )

        return response.json()