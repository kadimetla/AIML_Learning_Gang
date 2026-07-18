from dep_demo import hello


def test_hello():
    assert "poetry" in hello()
