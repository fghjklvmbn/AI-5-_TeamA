from pydantic import BaseModel


class SessionCreate(
    BaseModel
):

    session_name: str