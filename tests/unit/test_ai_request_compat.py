from src.services.ai_request_compat import (
    get_retry_after_seconds,
    is_json_output_unsupported_error,
    is_rate_limit_error,
    is_responses_api_unsupported_error,
    is_temperature_unsupported_error,
    remove_temperature_param,
)


def test_is_temperature_unsupported_error_detects_unsupported_message():
    err = Exception("temperature is not supported by this gateway")
    assert is_temperature_unsupported_error(err) is True


def test_remove_temperature_param_removes_only_temperature():
    params = {"model": "x", "temperature": 0.5, "max_output_tokens": 128}
    result = remove_temperature_param(params)

    assert "temperature" not in result
    assert result["model"] == "x"
    assert result["max_output_tokens"] == 128


def test_is_responses_api_unsupported_error_detects_gemini_plain_404():
    class _Resp:
        text = ""

    class _Err(Exception):
        status_code = 404
        body = ""
        response = _Resp()

        def __str__(self):
            return "Error code: 404"

    assert is_responses_api_unsupported_error(_Err()) is True


# -- is_json_output_unsupported_error tests --


def test_json_output_error_detected_via_body_param_response_format():
    """Vercel AI Gateway returns 400 with param='response_format'."""

    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "type": "invalid_request_error",
            "param": "response_format",
            "code": "invalid_request_error",
        }

    assert is_json_output_unsupported_error(_Err()) is True


def test_json_output_error_detected_via_body_param_response_format_type():
    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "param": "response_format.type",
        }

    assert is_json_output_unsupported_error(_Err()) is True


def test_json_output_error_detected_via_legacy_string_matching():
    err = Exception(
        "response_format.type is not supported by this model"
    )
    assert is_json_output_unsupported_error(err) is True


def test_json_output_error_not_triggered_by_unrelated_400():
    class _Err(Exception):
        body = {
            "message": "Invalid input",
            "param": "messages",
        }

    assert is_json_output_unsupported_error(_Err()) is False


def test_json_output_error_not_triggered_without_body():
    err = Exception("some random 400 error")
    assert is_json_output_unsupported_error(err) is False


# -- is_rate_limit_error / get_retry_after_seconds tests --


def test_is_rate_limit_error_detects_status_code_429():
    class _Err(Exception):
        status_code = 429

    assert is_rate_limit_error(_Err("boom")) is True


def test_is_rate_limit_error_detects_rate_limit_error_body_without_status_code():
    err = Exception(
        "Error code: 429 - {'type': 'error', 'error': {'type': 'rate_limit_error', "
        "'message': 'Token Plan 速率限制', 'http_code': '429'}}"
    )
    assert is_rate_limit_error(err) is True


def test_is_rate_limit_error_false_for_unrelated_error():
    assert is_rate_limit_error(Exception("temperature is unsupported")) is False


def test_get_retry_after_seconds_reads_header_when_present():
    class _Headers(dict):
        pass

    class _Resp:
        headers = _Headers({"retry-after": "12"})

    class _Err(Exception):
        response = _Resp()

    assert get_retry_after_seconds(_Err("boom")) == 12.0


def test_get_retry_after_seconds_returns_none_without_header():
    assert get_retry_after_seconds(Exception("boom")) is None
