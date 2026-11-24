import socket
from pathlib import Path


def _socket_path() -> Path:
    return Path.home() / ".config" / "phonotype" / "phonotype.sock"


def send_command(command: str) -> bool:
    """Send a one-word command to the running app; False when it is not running."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(_socket_path()))
        sock.sendall(command.encode("ascii"))
        return True
    except Exception as e:
        print(f"[IPC] Could not send '{command}' (is Phonotype running?): {e}")
        return False
    finally:
        sock.close()


def send_trigger():
    """Start or stop recording in the running app."""
    return send_command("trigger_record")
