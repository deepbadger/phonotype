import socket
import threading
from pathlib import Path

COMMANDS = ("trigger_record", "trigger_record_alt", "cancel_record", "paste_last", "paste_last_alt")


def _socket_path():
    return Path.home() / ".config" / "phonotype" / "phonotype.sock"


def start_ipc_server(trigger_callback, handlers: dict | None = None):
    """Listen in a background thread for one-word commands from `phonotype --…`.

    ``trigger_callback`` handles 'trigger_record'; ``handlers`` maps the other
    COMMANDS to callables. Unknown commands are ignored.
    """
    table = {"trigger_record": trigger_callback, **(handlers or {})}
    sock_path = _socket_path()
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen()

    def _serve_loop():
        while True:
            conn, _ = server.accept()
            try:
                command = conn.recv(1024).strip().decode("ascii", "ignore")
                handler = table.get(command)
                if handler:
                    handler()
            except Exception as e:      # a bad client must not stop the listener
                print(f"[IPC] {e}")
            finally:
                conn.close()

    t = threading.Thread(target=_serve_loop, daemon=True)
    t.start()
