from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


def test_dockerfile_runs_as_non_root():
    # #39: the container must drop privileges before running the app.
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER medcheck" in content
    # Every stage that defines a CMD should have switched away from root first.
    assert content.count("USER medcheck") >= content.count("CMD [")


def test_cloud_sdks_installed_in_both_images():
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert content.count("--extra cloud") == 2
    assert content.count('CMD ["/app/.venv/bin/medcheck", "serve"]') == 2
