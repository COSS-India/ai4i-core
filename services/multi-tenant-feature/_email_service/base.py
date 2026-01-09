from abc import ABC, abstractmethod

class EmailService(ABC):

    @abstractmethod
    async def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ):
        pass