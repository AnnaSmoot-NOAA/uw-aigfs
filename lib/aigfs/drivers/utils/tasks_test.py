from . import tasks

# Tests


def test_drivers_utils_file(tmp_path, logcap):
    path = tmp_path / "afile"
    assert not path.exists()
    assert not tasks.file(path=path).ready
    path.touch()
    node = tasks.file(path=path)
    assert node.ready
    assert node.ref == path
    assert f"File {path}" in logcap.text
