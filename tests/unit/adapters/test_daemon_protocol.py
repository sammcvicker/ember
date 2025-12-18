"""Unit tests for daemon protocol module."""

import json
import socket
from unittest.mock import MagicMock

import pytest

from ember.adapters.daemon.protocol import (
    ProtocolError,
    Request,
    Response,
    receive_message,
    send_message,
)


class TestRequest:
    """Tests for Request class."""

    def test_init_sets_method_params_and_id(self) -> None:
        """Test that __init__ correctly sets attributes."""
        request = Request(method="test_method", params={"key": "value"}, request_id=42)

        assert request.method == "test_method"
        assert request.params == {"key": "value"}
        assert request.id == 42

    def test_init_default_request_id_is_1(self) -> None:
        """Test that default request_id is 1."""
        request = Request(method="test", params={})

        assert request.id == 1

    def test_to_json_produces_valid_json(self) -> None:
        """Test that to_json produces valid JSON with newline."""
        request = Request(method="embed_texts", params={"texts": ["hello"]}, request_id=5)

        result = request.to_json()

        assert result.endswith("\n")
        data = json.loads(result.strip())
        assert data == {
            "method": "embed_texts",
            "params": {"texts": ["hello"]},
            "id": 5,
        }

    def test_to_json_handles_empty_params(self) -> None:
        """Test to_json with empty params dict."""
        request = Request(method="status", params={})

        result = request.to_json()
        data = json.loads(result.strip())

        assert data["params"] == {}

    def test_to_json_handles_complex_params(self) -> None:
        """Test to_json with complex nested params."""
        request = Request(
            method="embed",
            params={
                "texts": ["line1", "line2"],
                "options": {"model": "jina", "batch_size": 32},
            },
        )

        result = request.to_json()
        data = json.loads(result.strip())

        assert data["params"]["texts"] == ["line1", "line2"]
        assert data["params"]["options"]["model"] == "jina"

    def test_from_json_parses_valid_request(self) -> None:
        """Test from_json parses valid JSON request."""
        json_str = '{"method": "embed_texts", "params": {"key": "val"}, "id": 10}'

        request = Request.from_json(json_str)

        assert request.method == "embed_texts"
        assert request.params == {"key": "val"}
        assert request.id == 10

    def test_from_json_handles_newline(self) -> None:
        """Test from_json strips newlines."""
        json_str = '{"method": "test", "params": {}}\n'

        request = Request.from_json(json_str)

        assert request.method == "test"

    def test_from_json_default_params_is_empty_dict(self) -> None:
        """Test from_json uses empty dict when params is missing."""
        json_str = '{"method": "status"}'

        request = Request.from_json(json_str)

        assert request.params == {}

    def test_from_json_default_id_is_1(self) -> None:
        """Test from_json uses 1 when id is missing."""
        json_str = '{"method": "test", "params": {}}'

        request = Request.from_json(json_str)

        assert request.id == 1

    def test_from_json_raises_on_invalid_json(self) -> None:
        """Test from_json raises ProtocolError on invalid JSON."""
        with pytest.raises(ProtocolError) as exc_info:
            Request.from_json("not valid json {")

        assert "Invalid JSON" in str(exc_info.value)

    def test_from_json_raises_when_not_object(self) -> None:
        """Test from_json raises ProtocolError when JSON is not an object."""
        with pytest.raises(ProtocolError) as exc_info:
            Request.from_json("[]")

        assert "must be a JSON object" in str(exc_info.value)

    def test_from_json_raises_when_method_missing(self) -> None:
        """Test from_json raises ProtocolError when method is missing."""
        with pytest.raises(ProtocolError) as exc_info:
            Request.from_json('{"params": {}}')

        assert "missing 'method'" in str(exc_info.value)


class TestResponse:
    """Tests for Response class."""

    def test_init_sets_result_error_and_id(self) -> None:
        """Test that __init__ correctly sets attributes."""
        response = Response(result="data", error=None, request_id=5)

        assert response.result == "data"
        assert response.error is None
        assert response.id == 5

    def test_init_default_values(self) -> None:
        """Test default values for Response attributes."""
        response = Response()

        assert response.result is None
        assert response.error is None
        assert response.id == 1

    def test_to_json_produces_valid_json(self) -> None:
        """Test to_json produces valid JSON with newline."""
        response = Response(result={"embeddings": [[0.1, 0.2]]}, request_id=3)

        result = response.to_json()

        assert result.endswith("\n")
        data = json.loads(result.strip())
        assert data["result"] == {"embeddings": [[0.1, 0.2]]}
        assert data["error"] is None
        assert data["id"] == 3

    def test_to_json_with_error(self) -> None:
        """Test to_json with error response."""
        response = Response(error={"code": 500, "message": "Internal error"}, request_id=1)

        result = response.to_json()
        data = json.loads(result.strip())

        assert data["result"] is None
        assert data["error"]["code"] == 500
        assert data["error"]["message"] == "Internal error"

    def test_from_json_parses_success_response(self) -> None:
        """Test from_json parses valid success response."""
        json_str = '{"result": [1, 2, 3], "error": null, "id": 7}'

        response = Response.from_json(json_str)

        assert response.result == [1, 2, 3]
        assert response.error is None
        assert response.id == 7

    def test_from_json_parses_error_response(self) -> None:
        """Test from_json parses valid error response."""
        json_str = '{"result": null, "error": {"code": 404, "message": "Not found"}, "id": 2}'

        response = Response.from_json(json_str)

        assert response.result is None
        assert response.error == {"code": 404, "message": "Not found"}
        assert response.id == 2

    def test_from_json_handles_newline(self) -> None:
        """Test from_json strips newlines."""
        json_str = '{"result": "ok"}\n'

        response = Response.from_json(json_str)

        assert response.result == "ok"

    def test_from_json_default_id_is_1(self) -> None:
        """Test from_json uses 1 when id is missing."""
        json_str = '{"result": "data"}'

        response = Response.from_json(json_str)

        assert response.id == 1

    def test_from_json_raises_on_invalid_json(self) -> None:
        """Test from_json raises ProtocolError on invalid JSON."""
        with pytest.raises(ProtocolError) as exc_info:
            Response.from_json("not valid json")

        assert "Invalid JSON" in str(exc_info.value)

    def test_from_json_raises_when_not_object(self) -> None:
        """Test from_json raises ProtocolError when JSON is not an object."""
        with pytest.raises(ProtocolError) as exc_info:
            Response.from_json('"string"')

        assert "must be a JSON object" in str(exc_info.value)

    def test_success_creates_success_response(self) -> None:
        """Test success() factory method."""
        response = Response.success(result={"data": [1, 2]}, request_id=99)

        assert response.result == {"data": [1, 2]}
        assert response.error is None
        assert response.id == 99

    def test_success_default_request_id(self) -> None:
        """Test success() default request_id is 1."""
        response = Response.success(result="ok")

        assert response.id == 1

    def test_error_creates_error_response(self) -> None:
        """Test error() factory method."""
        response = Response.error(code=500, message="Server error", request_id=10)

        assert response.result is None
        assert response.error == {"code": 500, "message": "Server error"}
        assert response.id == 10

    def test_error_default_request_id(self) -> None:
        """Test error() default request_id is 1."""
        response = Response.error(code=400, message="Bad request")

        assert response.id == 1

    def test_is_error_returns_true_when_error_set(self) -> None:
        """Test is_error() returns True when error is set."""
        response = Response(error={"code": 500, "message": "error"})

        assert response.is_error() is True

    def test_is_error_returns_false_when_error_none(self) -> None:
        """Test is_error() returns False when error is None."""
        response = Response(result="ok", error=None)

        assert response.is_error() is False


class TestProtocolError:
    """Tests for ProtocolError exception."""

    def test_protocol_error_is_exception(self) -> None:
        """Test ProtocolError is an exception."""
        error = ProtocolError("Test error")

        assert isinstance(error, Exception)
        assert str(error) == "Test error"


class TestSendMessage:
    """Tests for send_message function."""

    def test_send_message_sends_encoded_json(self) -> None:
        """Test send_message sends JSON-encoded message."""
        mock_sock = MagicMock(spec=socket.socket)
        request = Request(method="test", params={"key": "value"})

        send_message(mock_sock, request)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        assert isinstance(sent_data, bytes)
        json_str = sent_data.decode("utf-8")
        assert json_str.endswith("\n")
        data = json.loads(json_str.strip())
        assert data["method"] == "test"

    def test_send_message_sends_response(self) -> None:
        """Test send_message works with Response objects."""
        mock_sock = MagicMock(spec=socket.socket)
        response = Response.success(result={"data": "value"}, request_id=5)

        send_message(mock_sock, response)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        data = json.loads(sent_data.decode("utf-8").strip())
        assert data["result"] == {"data": "value"}
        assert data["id"] == 5

    def test_send_message_raises_on_send_failure(self) -> None:
        """Test send_message raises ProtocolError on socket error."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.sendall.side_effect = OSError("Connection reset")
        request = Request(method="test", params={})

        with pytest.raises(ProtocolError) as exc_info:
            send_message(mock_sock, request)

        assert "Failed to send message" in str(exc_info.value)


class TestReceiveMessage:
    """Tests for receive_message function."""

    def test_receive_message_parses_request(self) -> None:
        """Test receive_message parses Request from socket."""
        mock_sock = MagicMock(spec=socket.socket)
        json_data = '{"method": "embed", "params": {"texts": ["hi"]}, "id": 1}\n'
        mock_sock.recv.return_value = json_data.encode("utf-8")

        result = receive_message(mock_sock, Request)

        assert isinstance(result, Request)
        assert result.method == "embed"
        assert result.params == {"texts": ["hi"]}

    def test_receive_message_parses_response(self) -> None:
        """Test receive_message parses Response from socket."""
        mock_sock = MagicMock(spec=socket.socket)
        json_data = '{"result": "ok", "error": null, "id": 3}\n'
        mock_sock.recv.return_value = json_data.encode("utf-8")

        result = receive_message(mock_sock, Response)

        assert isinstance(result, Response)
        assert result.result == "ok"
        assert result.id == 3

    def test_receive_message_handles_chunked_data(self) -> None:
        """Test receive_message handles data arriving in chunks."""
        mock_sock = MagicMock(spec=socket.socket)
        full_message = '{"method": "test", "params": {}}\n'
        # Simulate data arriving in two chunks
        mock_sock.recv.side_effect = [
            full_message[:10].encode("utf-8"),
            full_message[10:].encode("utf-8"),
        ]

        result = receive_message(mock_sock, Request)

        assert isinstance(result, Request)
        assert result.method == "test"

    def test_receive_message_raises_on_connection_closed(self) -> None:
        """Test receive_message raises ProtocolError when connection is closed."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.recv.return_value = b""  # Empty bytes = connection closed

        with pytest.raises(ProtocolError) as exc_info:
            receive_message(mock_sock, Request)

        assert "Connection closed" in str(exc_info.value)

    def test_receive_message_raises_on_invalid_json(self) -> None:
        """Test receive_message raises ProtocolError on invalid JSON."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.recv.return_value = b"not json\n"

        with pytest.raises(ProtocolError) as exc_info:
            receive_message(mock_sock, Request)

        assert "Invalid JSON" in str(exc_info.value)

    def test_receive_message_warns_on_extra_data(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test receive_message logs warning when extra data after newline."""
        mock_sock = MagicMock(spec=socket.socket)
        # Two messages in one recv call
        json_data = '{"method": "test", "params": {}}\nextra data'
        mock_sock.recv.return_value = json_data.encode("utf-8")

        result = receive_message(mock_sock, Request)

        assert result.method == "test"
        assert "bytes after first message delimiter" in caplog.text

    def test_receive_message_raises_on_recv_error(self) -> None:
        """Test receive_message raises ProtocolError on socket recv error."""
        mock_sock = MagicMock(spec=socket.socket)
        mock_sock.recv.side_effect = OSError("Network error")

        with pytest.raises(ProtocolError) as exc_info:
            receive_message(mock_sock, Request)

        assert "Failed to receive message" in str(exc_info.value)

    def test_receive_message_raises_on_oversized_message(self) -> None:
        """Test receive_message raises ProtocolError when message exceeds size limit."""
        mock_sock = MagicMock(spec=socket.socket)
        # Create a small max_size and send data that exceeds it
        max_size = 100
        # Each chunk is 50 bytes, so 3 chunks will exceed 100 bytes
        mock_sock.recv.side_effect = [
            b"x" * 50,  # 50 bytes
            b"x" * 50,  # 100 bytes total
            b"x" * 50,  # 150 bytes total - exceeds limit
        ]

        with pytest.raises(ProtocolError) as exc_info:
            receive_message(mock_sock, Request, max_size=max_size)

        assert "exceeds" in str(exc_info.value)
        assert "100" in str(exc_info.value)

    def test_receive_message_accepts_message_within_limit(self) -> None:
        """Test receive_message accepts messages within size limit."""
        mock_sock = MagicMock(spec=socket.socket)
        json_data = '{"method": "test", "params": {}}\n'
        mock_sock.recv.return_value = json_data.encode("utf-8")
        max_size = 1000  # Well above the message size

        result = receive_message(mock_sock, Request, max_size=max_size)

        assert isinstance(result, Request)
        assert result.method == "test"

    def test_receive_message_uses_default_max_size(self) -> None:
        """Test receive_message uses default max_size when not specified."""
        from ember.adapters.daemon.protocol import MAX_MESSAGE_SIZE

        mock_sock = MagicMock(spec=socket.socket)
        json_data = '{"method": "test", "params": {}}\n'
        mock_sock.recv.return_value = json_data.encode("utf-8")

        # Should work without specifying max_size
        result = receive_message(mock_sock, Request)

        assert isinstance(result, Request)
        assert MAX_MESSAGE_SIZE == 10 * 1024 * 1024  # 10MB default


class TestRoundTrip:
    """Integration tests for request/response round-trips."""

    def test_request_serialization_round_trip(self) -> None:
        """Test Request can be serialized and deserialized."""
        original = Request(
            method="embed_texts",
            params={"texts": ["hello", "world"], "model": "jina"},
            request_id=42,
        )

        json_str = original.to_json()
        restored = Request.from_json(json_str)

        assert restored.method == original.method
        assert restored.params == original.params
        assert restored.id == original.id

    def test_response_serialization_round_trip(self) -> None:
        """Test Response can be serialized and deserialized."""
        original = Response(
            result={"embeddings": [[0.1, 0.2, 0.3]]},
            error=None,
            request_id=42,
        )

        json_str = original.to_json()
        restored = Response.from_json(json_str)

        assert restored.result == original.result
        assert restored.error == original.error
        assert restored.id == original.id

    def test_error_response_serialization_round_trip(self) -> None:
        """Test error Response can be serialized and deserialized."""
        original = Response.error(code=500, message="Internal error", request_id=99)

        json_str = original.to_json()
        restored = Response.from_json(json_str)

        assert restored.result is None
        assert restored.error == {"code": 500, "message": "Internal error"}
        assert restored.id == 99
