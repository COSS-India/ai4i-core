class UltimatelyDLQException(Exception):
    """Raised by a handler when a message is unrecoverable and must be sent to the DLQ.

    The consumer will forward the original message to the DLQ topic and commit
    the offset so the message is never retried.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = ["UltimatelyDLQException"]