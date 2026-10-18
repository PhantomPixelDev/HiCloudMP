def test_main_imports_without_linux_backends():
    """Task 3 regression: importing main on a machine without dbus/gi (Windows)
    must not raise ImportError — MPRIS support degrades to a no-op."""
    import main

    assert main.MprisService is None or hasattr(main.MprisService, "start")
