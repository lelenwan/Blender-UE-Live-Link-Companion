import socket
import time

try:
    from . import live_link_protocol
except ImportError:
    import live_link_protocol


SKELETON_RESEND_SECONDS = 2.0


class LiveLinkSender:
    def __init__(self, *, clock=None):
        self._clock = clock or time.monotonic
        self._socket = None
        self._destination = None
        self._host = "127.0.0.1"
        self._port = 0
        self._subject = "BlenderUELiveLink"
        self._fps = 30
        self._sequence = 0
        self._packets_sent = 0
        self._bytes_sent = 0
        self._errors = 0
        self._last_error = ""
        self._last_skeleton_sent = None
        self._cached_skeleton = None

    def start(self, *, host, port, subject, fps):
        if host != "127.0.0.1":
            raise ValueError("Live Link host must be 127.0.0.1")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("Live Link port must be between 1 and 65535")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Live Link subject must be a non-empty string")
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240:
            raise ValueError("Live Link FPS must be between 1 and 240")

        self.stop()
        sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender_socket.setblocking(False)
        self._socket = sender_socket
        self._destination = (host, port)
        self._host = host
        self._port = port
        self._subject = subject
        self._fps = fps
        self._sequence = 0
        self._packets_sent = 0
        self._bytes_sent = 0
        self._errors = 0
        self._last_error = ""
        self._last_skeleton_sent = None
        self._cached_skeleton = None

    def stop(self):
        sender_socket = self._socket
        self._socket = None
        self._destination = None
        self._cached_skeleton = None
        self._last_skeleton_sent = None
        if sender_socket is not None:
            sender_socket.close()

    def _require_running(self):
        if self._socket is None or self._destination is None:
            raise RuntimeError("Live Link sender is not running")

    def _record_error(self, exc):
        self._errors += 1
        self._last_error = str(exc)

    def _send_payload(self, payload, sequence):
        self._require_running()
        bytes_sent = self._socket.sendto(payload, self._destination)
        if bytes_sent != len(payload):
            raise OSError(f"partial UDP datagram send: {bytes_sent}/{len(payload)}")
        self._sequence = sequence
        self._packets_sent += 1
        self._bytes_sent += bytes_sent
        self._last_error = ""

    def _send_skeleton_packet(self, bone_names, bone_parents):
        sequence = self._sequence + 1
        payload = live_link_protocol.encode_skeleton(
            subject=self._subject,
            sequence=sequence,
            bone_names=bone_names,
            bone_parents=bone_parents,
        )
        self._send_payload(payload, sequence)
        self._last_skeleton_sent = self._clock()

    def send_skeleton(self, bone_names, bone_parents):
        self._require_running()
        try:
            names = list(bone_names)
            parents = list(bone_parents)
            self._send_skeleton_packet(names, parents)
            self._cached_skeleton = (names, parents)
        except Exception as exc:
            self._record_error(exc)
            raise

    def send_frame(self, time_seconds, transforms):
        self._require_running()
        try:
            now = self._clock()
            if (
                self._cached_skeleton is not None
                and self._last_skeleton_sent is not None
                and now - self._last_skeleton_sent >= SKELETON_RESEND_SECONDS
            ):
                self._send_skeleton_packet(*self._cached_skeleton)

            sequence = self._sequence + 1
            payload = live_link_protocol.encode_frame(
                subject=self._subject,
                sequence=sequence,
                time_seconds=time_seconds,
                transforms=transforms,
            )
            self._send_payload(payload, sequence)
        except Exception as exc:
            self._record_error(exc)
            raise

    def snapshot(self):
        return {
            "running": self._socket is not None,
            "host": self._host,
            "port": self._port,
            "subject": self._subject,
            "fps": self._fps,
            "last_sequence": self._sequence,
            "packets_sent": self._packets_sent,
            "bytes_sent": self._bytes_sent,
            "errors": self._errors,
            "last_error": self._last_error,
            "last_skeleton_sent": self._last_skeleton_sent,
        }
