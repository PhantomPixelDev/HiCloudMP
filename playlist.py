import uuid
from datetime import datetime

class Playlist:
    """Class representing a music playlist."""
    def __init__(self, name="New Playlist", items=None):
        self.id = str(uuid.uuid4())  # Unique ID for the playlist
        self.name = name
        self.items = items or []  # List of tracks (can be local files or cloud references)
        self.created = datetime.now().isoformat()
        self.modified = self.created
    
    def add_item(self, item):
        """Add an item to the playlist"""
        self.items.append(item)
        self.modified = datetime.now().isoformat()
    
    def remove_item(self, index):
        """Remove an item at the specified index"""
        if 0 <= index < len(self.items):
            del self.items[index]
            self.modified = datetime.now().isoformat()
    
    def move_item(self, from_index, to_index):
        """Move an item from one position to another"""
        if 0 <= from_index < len(self.items) and 0 <= to_index < len(self.items):
            item = self.items.pop(from_index)
            self.items.insert(to_index, item)
            self.modified = datetime.now().isoformat()
    
    def to_dict(self):
        """Convert playlist to dictionary for serialization"""
        return {
            "id": self.id,
            "name": self.name,
            "items": self.items,
            "created": self.created,
            "modified": self.modified
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create playlist from dictionary"""
        playlist = cls(data["name"], data["items"])
        playlist.id = data["id"]
        playlist.created = data["created"]
        playlist.modified = data["modified"]
        return playlist 