"""JSON-RPC protocol for daemon communication.

Simple JSON-RPC-style protocol over Unix sockets with newline-delimited messages.
"""

import json
from typing import Any


class ProtocolError(Exception):
    """Base exception for protocol errors."""

    pass


class Request:
    """JSON-RPC request message."""

    def __init__(self, method: str, params: dict[str, Any], request_id: int = 1):
        """Create a request.

        Args:
            method: Method name (e.g., "embed_texts")
            params: Method parameters
            request_id: Request ID for matching responses
        """
        self.method = method
        self.params = params
        self.id = request_id

    def to_json(self) -> str:
        """Serialize to JSON string with newline."""
        data = {"method": self.method, "params": self.params, "id": self.id}
        return json.dumps(data) + "\n"

    @classmethod
    def from_json(cls, line: str) -> "Request":
        """Deserialize from JSON string.

        Args:
            line: JSON string (with or without newline)

        Returns:
            Request object

        Raises:
            ProtocolError: If JSON is invalid or missing required fields
        """
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise ProtocolError("Request must be a JSON object")

        if "method" not in data:
            raise ProtocolError("Request missing 'method' field")

        return cls(
            method=data["method"],
            params=data.get("params", {}),
            request_id=data.get("id", 1),
        )


class Response:
    """JSON-RPC response message."""

    def __init__(
        self,
        result: Any = None,
        error: dict[str, Any] | None = None,
        request_id: int = 1,
    ):
        """Create a response.

        Args:
            result: Result value (if success)
            error: Error dict with 'code' and 'message' (if failure)
            request_id: Request ID for matching requests
        """
        self.result = result
        self.error = error
        self.id = request_id

    def to_json(self) -> str:
        """Serialize to JSON string with newline."""
        data = {"result": self.result, "error": self.error, "id": self.id}
        return json.dumps(data) + "\n"

    @classmethod
    def from_json(cls, line: str) -> "Response":
        """Deserialize from JSON string.

        Args:
            line: JSON string (with or without newline)

        Returns:
            Response object

        Raises:
            ProtocolError: If JSON is invalid
        """
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError as e:
            raise ProtocolError(f"Invalid JSON: {e}") from e

        if not isinstance(data, dict):
            raise ProtocolError("Response must be a JSON object")

        return cls(
            result=data.get("result"),
            error=data.get("error"),
            request_id=data.get("id", 1),
        )

    @classmethod
    def success(cls, result: Any, request_id: int = 1) -> "Response":
        """Create a success response."""
        return cls(result=result, error=None, request_id=request_id)

    @classmethod
    def error(cls, code: int, message: str, request_id: int = 1) -> "Response":
        """Create an error response."""
        return cls(result=None, error={"code": code, "message": message}, request_id=request_id)

    def is_error(self) -> bool:
        """Check if this response is an error."""
        return self.error is not None


def send_message(sock, message: Request | Response) -> None:
    """Send a message over a socket.

    Args:
        sock: Socket to send on
        message: Request or Response to send

    Raises:
        ProtocolError: If send fails
    """
    try:
        data = message.to_json().encode("utf-8")
        sock.sendall(data)
    except Exception as e:
        raise ProtocolError(f"Failed to send message: {e}") from e


def receive_message(sock, message_type: type[Request] | type[Response]) -> Request | Response:
    """Receive a message from a socket.

    Args:
        sock: Socket to receive from
        message_type: Type of message to expect (Request or Response)

    Returns:
        Received message

    Raises:
        ProtocolError: If receive fails or message is invalid
    """
    try:
        # Read until newline
        buffer = b""
        while True:
            chunk = sock.recv(1024)
            if not chunk:
                raise ProtocolError("Connection closed")
            buffer += chunk
            if b"\n" in buffer:
                break

        # Parse first complete message
        line = buffer.split(b"\n", 1)[0].decode("utf-8")
        return message_type.from_json(line)
    except ProtocolError:
        raise
    except Exception as e:
        raise ProtocolError(f"Failed to receive message: {e}") from e
