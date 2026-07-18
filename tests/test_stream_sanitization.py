import pytest

from hogflow.core import ConfigurationError
from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.sanitization import redact_camera_secrets


def _synthetic_rtsp_url() -> tuple[str, str, str]:
    user = "unit" + "-account"
    secret = "runtime" + "-value"
    host = ".".join(("198", "51", "100", "7"))
    return "rt" + f"sp://{user}:{secret}@{host}:8554/live", user, secret


def test_rtsp_configuration_repr_and_identity_hide_locator() -> None:
    url, user, secret = _synthetic_rtsp_url()
    configuration = StreamConfiguration.rtsp("north-gate", url)
    rendered = (
        repr(configuration) + repr(configuration.protected_source) + repr(configuration.identity)
    )

    assert user not in rendered
    assert secret not in rendered
    assert "198.51.100.7" not in rendered
    assert url not in rendered
    assert configuration.identity.display_name == "rtsp-camera:north-gate"


def test_redaction_removes_complete_rtsp_reference() -> None:
    url, user, secret = _synthetic_rtsp_url()
    output = redact_camera_secrets(f"backend rejected {url} during setup")

    assert output == "backend rejected rtsp://<redacted> during setup"
    assert user not in output
    assert secret not in output


def test_invalid_rtsp_url_raises_only_sanitized_message() -> None:
    raw = "not-a-camera-locator"
    with pytest.raises(ConfigurationError) as captured:
        StreamConfiguration.rtsp("camera", raw)

    assert raw not in str(captured.value)


def test_malformed_rtsp_authority_never_leaks_credentials() -> None:
    secret = "malformed" + "-runtime-value"
    raw = "rt" + f"sp://unit:{secret}@[invalid/live"

    with pytest.raises(ConfigurationError) as captured:
        StreamConfiguration.rtsp("camera", raw)

    assert secret not in str(captured.value)
    assert raw not in str(captured.value)


def test_stream_id_rejects_sensitive_field_terminology() -> None:
    with pytest.raises(ConfigurationError, match="sensitive"):
        StreamConfiguration.usb("camera-secret")


def test_file_configuration_repr_hides_windows_and_posix_paths() -> None:
    for path in (
        "C:/" + "Users/synthetic account/private camera.mp4",
        "/" + "home/synthetic account/private camera.mp4",
    ):
        configuration = StreamConfiguration.file("local-regression", path)
        rendered = repr(configuration) + repr(configuration.protected_source)
        assert path not in rendered
        assert "synthetic account" not in rendered


def test_stream_identity_rejects_path_like_display_name() -> None:
    from hogflow.streaming.models import SourceType, StreamIdentity

    with pytest.raises(Exception, match="unsafe"):
        StreamIdentity("camera", SourceType.RTSP, "rtsp://unsafe")
