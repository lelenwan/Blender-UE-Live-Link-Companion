"""Local, data-only character exchange; no Blender dependency."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

PROTOCOL = 1
SESSION_MAX_AGE = 15.0
REQUEST_TIMEOUT = 300.0
HEX_ID = re.compile(r'^[0-9a-f]{32}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
ASSET_ROOT = re.compile(r'^/Game/BlenderLiveLink(?:/[A-Za-z_][A-Za-z0-9_]*)*$')


def session_directory():
    return Path(os.environ.get('BLENDER_UE_LIVELINK_SESSION_DIR') or
                str(Path(tempfile.gettempdir()) / 'BlenderUELiveLink/Sessions'))


def read_json(path, maximum=1024 * 1024):
    path = Path(path)
    if path.stat().st_size > maximum:
        raise ValueError('同步记录过大。')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def reject_links(path):
    for item in [Path(path), *Path(path).parents]:
        if item.is_symlink() or (item.exists() and
                getattr(item.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('同步目录不能使用符号链接或目录联接。')


def safe_join(root, relative):
    root = Path(root)
    part = Path(relative)
    if part.is_absolute() or '..' in part.parts or not part.parts:
        raise ValueError('同步文件路径不正确。')
    reject_links(root)
    result = root / part
    reject_links(result)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('同步文件超出目标目录。')
    return result


def atomic_json(path, value):
    path = Path(path)
    reject_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_session(record, now=None):
    now = time.time() if now is None else now
    if not isinstance(record, dict) or record.get('protocol') != PROTOCOL:
        raise ValueError('UE 同步插件协议不兼容。')
    if not HEX_ID.fullmatch(str(record.get('session_id', ''))):
        raise ValueError('UE 会话标识不正确。')
    heartbeat = float(record.get('heartbeat', 0))
    if not 0 <= now - heartbeat <= SESSION_MAX_AGE:
        raise ValueError('UE 工程已关闭或未响应，请刷新工程列表。')
    project = Path(record.get('project_file', ''))
    if not project.is_absolute() or project.suffix.lower() != '.uproject' or not project.is_file():
        raise ValueError('UE 工程路径不可用。')
    mailbox = Path(record.get('mailbox', ''))
    expected = project.parent / 'Saved/BlenderUELiveLink' / record['session_id']
    reject_links(project)
    reject_links(mailbox)
    if not mailbox.is_absolute() or mailbox.resolve() != expected.resolve():
        raise ValueError('UE 同步目录与工程不匹配。')
    port = int(record.get('udp_port', 0))
    if not 0 <= port <= 65535:
        raise ValueError('UE 接收端口不正确。')
    static_port = int(record.get('static_udp_port', 0))
    if not 0 <= static_port <= 65535:
        raise ValueError('UE 静态模型接收端口不正确。')
    return record


def discover_sessions(directory=None, now=None, diagnostics=None):
    directory = Path(directory) if directory is not None else session_directory()
    if diagnostics is not None:
        diagnostics.update(directory=str(directory), rejected=[])
    sessions = []
    if not directory.is_dir():
        return sessions
    reject_links(directory)
    for path in sorted(directory.glob('*.json'))[:256]:
        try:
            record = validate_session(read_json(path), now)
            if path.stem != record['session_id']:
                continue
            sessions.append(record)
        except (OSError, ValueError, TypeError, KeyError) as error:
            if diagnostics is not None:
                diagnostics['rejected'].append(str(error))
            continue
    return sessions


def refresh_session(session_id, directory=None):
    if not HEX_ID.fullmatch(str(session_id)):
        raise ValueError('请先选择正在运行的 UE 工程。')
    path = (Path(directory) if directory is not None else session_directory()) / (session_id + '.json')
    try:
        return validate_session(read_json(path))
    except OSError as error:
        raise ValueError('找不到所选 UE 工程，请刷新列表。') from error


def allocate_payload(session, request_id=None):
    validate_session(session)
    request_id = request_id or uuid.uuid4().hex
    if not HEX_ID.fullmatch(request_id):
        raise ValueError('同步请求标识不正确。')
    folder = safe_join(session['mailbox'], 'payloads/' + request_id)
    folder.mkdir(parents=True, exist_ok=False)
    return request_id, folder


def publish_request(session, request_id, metadata):
    validate_session(session)
    if not HEX_ID.fullmatch(request_id) or not HEX_ID.fullmatch(str(metadata.get('role_id', ''))):
        raise ValueError('角色或请求标识不正确。')
    if metadata.get('operation') not in ('sync', 'update'):
        raise ValueError('同步操作不正确。')
    model_type = metadata.get('model_type', 'skeletal')
    if model_type not in ('skeletal', 'static'):
        raise ValueError('同步模型类型不正确。')
    if model_type == 'static':
        if 'static_mesh_v1' not in session.get('capabilities', []):
            raise ValueError('目标 UE 插件尚不支持静态模型，请升级 UE 插件。')
        transform = metadata.get('transform')
        if (not isinstance(transform, list) or len(transform) != 10 or
                any(isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) for value in transform)):
            raise ValueError('静态模型变换不正确。')
        if not 0.99 <= sum(value * value for value in transform[3:7]) <= 1.01:
            raise ValueError('静态模型旋转四元数未归一化。')
        if any(abs(value) > 1e9 for value in transform[:3]) or any(
                not 1e-8 <= value <= 1e6 for value in transform[7:]):
            raise ValueError('静态模型位置或缩放超出支持范围。')
    if not ASSET_ROOT.fullmatch(metadata.get('asset_root', '')):
        raise ValueError('资源目录须位于 /Game/BlenderLiveLink 下，且只包含英文字母、数字和下划线。')
    relative = 'payloads/' + request_id + '/character.fbx'
    fbx = safe_join(session['mailbox'], relative)
    if not fbx.is_file() or not fbx.stat().st_size:
        raise ValueError('模型 FBX 未成功导出。')
    request = dict(metadata, protocol=PROTOCOL, request_id=request_id,
                   session_id=session['session_id'], fbx=relative, fbx_sha256=file_sha256(fbx))
    path = safe_join(session['mailbox'], 'requests/' + request_id + '.json')
    if path.exists():
        raise ValueError('同步请求已提交。')
    atomic_json(path, request)
    return request


def read_response(session, request_id, role_id):
    if not HEX_ID.fullmatch(request_id):
        raise ValueError('同步请求标识不正确。')
    path = safe_join(session['mailbox'], 'responses/' + request_id + '.json')
    if not path.exists():
        return None
    result = read_json(path)
    if (not isinstance(result, dict) or result.get('protocol') != PROTOCOL or
            result.get('request_id') != request_id or result.get('session_id') != session['session_id'] or
            result.get('role_id') != role_id or result.get('status') not in ('ok', 'error')):
        raise ValueError('UE 返回的同步结果与当前角色不匹配。')
    if result['status'] == 'ok':
        model_type = result.get('model_type', 'skeletal')
        if model_type not in ('skeletal', 'static'):
            raise ValueError('UE 返回的模型类型不正确。')
        port_key = 'static_udp_port' if model_type == 'static' else 'udp_port'
        if not 1 <= int(result.get(port_key, 0)) <= 65535:
            raise ValueError('UE 未返回可用的模型接收端口。')
    return result
