import os

from conftest import session_appdata


def test_config_paths_under_session_appdata():
    """utils module must resolve all config files inside the isolated test APPDATA."""
    import utils

    base = str(session_appdata()).replace("\\", "/").lower() + "/"
    for path in (utils.data_dir, utils.MEDIA_FOLDERS_FILE, utils.CLOUD_FILES_FILE, utils.PLAYLISTS_FILE):
        assert str(path).replace("\\", "/").lower().startswith(base), f"{path} escapes session APPDATA"
