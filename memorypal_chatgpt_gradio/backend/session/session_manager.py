import uuid


class SessionManager:

    @staticmethod
    def create_local_session():

        return str(
            uuid.uuid4()
        )