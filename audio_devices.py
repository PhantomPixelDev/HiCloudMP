"""Audio output device enumeration + settings resolution."""
from PySide6.QtMultimedia import QMediaDevices


def list_output_devices():
    """[(id_str, description)] with ('', 'System default') first."""
    out = [("", "System default")]
    try:
        for d in QMediaDevices.audioOutputs():
            did = bytes(d.id()).decode("utf-8", "replace")
            desc = str(d.description() or "Audio device")
            out.append((did, desc))
    except Exception:
        pass
    return out


def resolve_output(device_id):
    """QAudioDevice for `device_id`; None for empty/garbage except that ''
    resolves to the system default. Returns None only if no device exists
    (than system default is unusable)."""
    try:
        if str(device_id or ""):
            for d in QMediaDevices.audioOutputs():
                if bytes(d.id()).decode("utf-8", "replace") == str(device_id):
                    return d
            return None
        return _default()
    except Exception:
        return None


def _default():
    try:
        d = QMediaDevices().defaultAudioOutput()
        if d is not None and not d.isNull():
            return d
    except Exception:
        pass
    try:
        devices = QMediaDevices.audioOutputs()
        if devices:
            return devices[0]
    except Exception:
        pass
    return None
