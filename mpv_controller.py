import socket
import json
import os

class MPVController:
    def __init__(self, socket_path="/tmp/mpvsocket"):
        self.socket_path = socket_path
        self.sock = None

    def connect(self):
        if self.sock:
            return
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.connect(self.socket_path)
        except Exception as e:
            print(f"Could not connect to mpv socket: {e}")
            self.sock = None

    def send_command(self, command, args=None):
        self.connect()
        if not self.sock:
            return
        msg = {"command": [command] + (args or [])}
        try:
            self.sock.send((json.dumps(msg) + "\n").encode())
        except Exception as e:
            print(f"Failed to send command: {e}")

    def set_property(self, prop, value):
        self.send_command("set_property", [prop, value])


    def get_property(self, prop):
        self.connect()
        if not self.sock:
            return None
        msg = {"command": ["get_property", prop]}
        try:
            self.sock.send((json.dumps(msg) + "\n").encode())
            buffer = b""
            while True:
                chunk = self.sock.recv(1024)
                if not chunk:
                    break
                buffer += chunk
                try:
                    lines = buffer.decode().splitlines()
                    for line in lines:
                        if line.strip():
                            parsed = json.loads(line)
                            return parsed.get("data")
                except json.JSONDecodeError:
                    continue  # wait for more complete JSON
        except (BrokenPipeError, OSError, json.JSONDecodeError):
            print(f"mpv disconnected. Property '{prop}' failed.")
            self.sock = None
            return None
