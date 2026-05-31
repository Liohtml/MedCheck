from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[2] / "Dockerfile"


def test_dockerfile_runs_as_non_root():
    # #39: the container must drop privileges before running the app.
    content = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER medcheck" in content
    # Every stage that defines a CMD should have switched away from root first.
    assert content.count("USER medcheck") >= content.count("CMD [")
