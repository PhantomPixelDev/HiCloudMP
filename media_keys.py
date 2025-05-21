from PySide6.QtCore import QObject, QEvent, Qt
from utils import HAS_WIN32

if HAS_WIN32:
    import win32con
    import win32gui
    import win32api

class MediaKeyEventFilter(QObject):
    """Global event filter to capture media keys on various platforms"""
    def __init__(self, player):
        super().__init__()
        self.player = player
        
    def eventFilter(self, obj, event):
        # Handle key press events
        if event.type() == QEvent.KeyPress:
            key = event.key()
            
            # Check for media keys
            if key == Qt.Key_MediaPlay or key == Qt.Key_MediaTogglePlayPause:
                self.player.toggle_play()
                return True
            elif key == Qt.Key_MediaNext:
                self.player.next_track()
                return True
            elif key == Qt.Key_MediaPrevious:
                self.player.prev_track()
                return True
            elif key == Qt.Key_MediaStop:
                self.player.stop()
                return True
                
        # Let other events pass through
        return super().eventFilter(obj, event)

def setup_windows_media_keys(window):
    """Set up Windows-specific media key handling using win32api"""
    if not HAS_WIN32:
        return
        
    try:
        # Define Windows media key constants if not already defined
        if not hasattr(win32con, 'VK_MEDIA_PLAY_PAUSE'):
            win32con.VK_MEDIA_PLAY_PAUSE = 0xB3
            win32con.VK_MEDIA_STOP = 0xB2
            win32con.VK_MEDIA_PREV_TRACK = 0xB1
            win32con.VK_MEDIA_NEXT_TRACK = 0xB0
        
        # Register for Windows messages
        window.old_win_proc = win32gui.SetWindowLong(
            int(window.winId()),
            win32con.GWL_WNDPROC,
            window.win_proc
        )
        
        # Register hot keys
        try:
            win32api.RegisterHotKey(int(window.winId()), 1, 0, win32con.VK_MEDIA_PLAY_PAUSE)
            win32api.RegisterHotKey(int(window.winId()), 2, 0, win32con.VK_MEDIA_STOP)
            win32api.RegisterHotKey(int(window.winId()), 3, 0, win32con.VK_MEDIA_PREV_TRACK)
            win32api.RegisterHotKey(int(window.winId()), 4, 0, win32con.VK_MEDIA_NEXT_TRACK)
            print("Windows media keys registered successfully")
        except Exception as e:
            print(f"Failed to register Windows media keys: {e}")
    except Exception as e:
        print(f"Error setting up Windows media keys: {e}")

def cleanup_windows_media_keys(window):
    """Clean up Windows media key registration"""
    if not HAS_WIN32:
        return
        
    try:
        win32api.UnregisterHotKey(int(window.winId()), 1)
        win32api.UnregisterHotKey(int(window.winId()), 2)
        win32api.UnregisterHotKey(int(window.winId()), 3)
        win32api.UnregisterHotKey(int(window.winId()), 4)
        
        # Restore original window procedure
        if hasattr(window, 'old_win_proc'):
            win32gui.SetWindowLong(
                int(window.winId()),
                win32con.GWL_WNDPROC,
                window.old_win_proc
            )
    except Exception as e:
        print(f"Error cleaning up Windows media keys: {e}")

def create_win_proc_handler(player):
    """Create a Windows message handler function for media keys"""
    def win_proc(hwnd, msg, wparam, lparam):
        """Windows message handler for media keys"""
        if msg == win32con.WM_HOTKEY:
            # Get the ID
            id = wparam
            
            # Dispatch to appropriate handler
            if id == 1:  # Play/Pause
                player.toggle_play()
                return 0
            elif id == 2:  # Stop
                player.stop()
                return 0
            elif id == 3:  # Previous
                player.prev_track()
                return 0
            elif id == 4:  # Next
                player.next_track()
                return 0
        
        # Call original window procedure for other messages
        return win32gui.CallWindowProc(player.old_win_proc, hwnd, msg, wparam, lparam)
    
    return win_proc 