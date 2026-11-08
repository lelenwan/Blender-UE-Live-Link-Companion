"""Small loopback-only static object transform stream; legacy pose wire stays unchanged."""
import json
import math
import re
import socket
import time

HEX_ID = re.compile(r'^[0-9a-f]{32}$')
MAX_SEQUENCE = 9007199254740991
MAX_PACKET_BYTES = 4096


def validate_transform(transform):
    if (not isinstance(transform, (list, tuple)) or len(transform) != 10 or
            any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) for value in transform)):
        raise ValueError('静态模型变换必须是 10 个有限数值。')
    values = [float(value) for value in transform]
    if any(abs(value) > 1e9 for value in values[:3]):
        raise ValueError('静态模型位置超出支持范围。')
    length = sum(value * value for value in values[3:7])
    if not 0.99 <= length <= 1.01:
        raise ValueError('静态模型旋转四元数未归一化。')
    if any(not 1e-8 <= value <= 1e6 for value in values[7:]):
        raise ValueError('静态模型仅支持正数缩放，暂不支持镜像或零缩放。')
    return values


class StaticTransformSender:
    def __init__(self):
        self._socket = None
        self._sequence = 0
        self._session_id = ''
        self._role_id = ''
        self._port = 0
        self._fps = 30
        self._sent_frames = 0
        self._last_error = ''
        self._last_send_time = None

    def start(self, *, host='127.0.0.1', port, session_id, role_id, fps=30):
        if host != '127.0.0.1':
            raise ValueError('静态模型同步仅支持本机回环地址。')
        if (isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 or
                not HEX_ID.fullmatch(str(session_id)) or not HEX_ID.fullmatch(str(role_id))):
            raise ValueError('静态模型接收端口或会话标识不正确。')
        self.stop()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._session_id, self._role_id, self._port = session_id, role_id, port
        self._fps = max(1, min(120, int(fps)))
        self._last_error = ''

    def stop(self):
        if self._socket is not None:
            self._socket.close()
        self._socket = None

    def send_transform(self, transform):
        if self._socket is None:
            raise ValueError('静态模型变换发送尚未启动。')
        values = validate_transform(transform)
        if self._sequence >= MAX_SEQUENCE:
            self.stop()
            raise ValueError('发送序号已达上限，请重新加载插件。')
        next_sequence = self._sequence + 1
        packet = {'protocol': 1, 'session_id': self._session_id, 'role_id': self._role_id,
                  'sequence': next_sequence, 'transform': values}
        encoded = json.dumps(packet, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(encoded) > MAX_PACKET_BYTES:
            raise ValueError('静态模型变换数据包过大。')
        try:
            self._socket.sendto(encoded, ('127.0.0.1', self._port))
        except OSError as error:
            self._last_error = str(error)
            self.stop()
            raise
        self._sequence = next_sequence
        self._sent_frames += 1
        self._last_send_time = time.monotonic()
        self._last_error = ''

    def snapshot(self):
        return {'running': self._socket is not None, 'last_sequence': self._sequence,
                'sent_frames': self._sent_frames, 'last_error': self._last_error,
                'last_send_time': self._last_send_time, 'fps': self._fps,
                'session_id': self._session_id, 'role_id': self._role_id, 'port': self._port}
