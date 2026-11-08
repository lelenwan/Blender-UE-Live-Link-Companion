# Copyright (c) 2026 YanNick (localization and maintenance modifications).
bl_info = {
    'name': 'Blender UE Live Link',
    'author': 'YanNick',
    'version': (0, 6, 5),
    'blender': (5, 0, 0),
    'location': 'View3D > Sidebar > UE Live Link',
    'description': 'Sync static or skinned models and stream transforms to a local Unreal project',
    'category': 'Animation',
}

import importlib
import time
import textwrap
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

_previous_sender = globals().get('_live_link_sender')
if _previous_sender is not None:
    _previous_sender.stop()
_previous_static_sender = globals().get('_static_transform_sender')
if _previous_static_sender is not None:
    _previous_static_sender.stop()
for _timer_name in ('_live_link_stream_timer', '_character_sync_timer'):
    _previous_timer = globals().get(_timer_name)
    if _previous_timer is not None and bpy.app.timers.is_registered(_previous_timer):
        bpy.app.timers.unregister(_previous_timer)
for _handlers in (bpy.app.handlers.save_post, bpy.app.handlers.load_pre):
    for _handler in list(_handlers):
        if getattr(_handler, '_blender_ue_sync_handler', False):
            _handlers.remove(_handler)

from . import (api_compat, live_link_protocol, live_link_pose, live_link_sender, character_sync_client,
               character_export, static_sender, static_export, character_preprocess, i18n)
i18n = importlib.reload(i18n)
api_compat = importlib.reload(api_compat)
live_link_protocol = importlib.reload(live_link_protocol)
live_link_pose = importlib.reload(live_link_pose)
live_link_sender = importlib.reload(live_link_sender)
character_sync_client = importlib.reload(character_sync_client)
character_export = importlib.reload(character_export)
static_sender = importlib.reload(static_sender)
static_export = importlib.reload(static_export)
character_preprocess = importlib.reload(character_preprocess)

_live_link_sender = live_link_sender.LiveLinkSender()
_static_transform_sender = static_sender.StaticTransformSender()
_live_link_last_ui_error = ''
_sessions = {}
_session_enum_items = [('NONE', 'Select a UE Project', 'Refresh and select a running UE project')]
_session_enum_numbers = {}
_pending = None
_synced_roles = {}
_auto_binding = None
_automatic_due = None
_stream_armature = None
_stream_skeleton = None
_stream_static_object = None
_stream_preparation_guard = None
_stream_model_type = ''
_stream_role_id = ''
_stream_session_id = ''
_next_session_poll = 0.0
_discovery_status = '正在查找运行中的 UE 工程…'
_discovery_details = ''
LIVE_LINK_SUBJECT = 'BlenderUELiveLink'


def _settings():
    return getattr(getattr(bpy.context, 'window_manager', None), 'blender_ue_live_link_settings', None)


def _tag_view3d_redraw():
    manager = getattr(bpy.context, 'window_manager', None)
    if manager is not None:
        for window in manager.windows:
            if window.screen is not None:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()


def _poll_armature(_settings, obj):
    try:
        armature = character_export.find_armature(bpy.context, obj) if obj is not None else None
        return bool(armature is not None and character_export.meshes_for(armature, bpy.context.scene)
                    and any(b.use_deform for b in armature.data.bones))
    except ValueError:
        return False


def _on_armature_changed(self, context):
    target = self.live_link_armature
    if target is None:
        return
    try:
        armature = character_export.find_armature(context, target)
        if armature is None or not character_export.meshes_for(armature, context.scene):
            raise ValueError('请选择带 Armature 修改器的蒙皮模型或其绑定骨架。')
        if _stream_armature is not None and _stream_armature != armature:
            _stop_stream()
        if self.sync_auto_save and _auto_binding is not None and _auto_binding[1] != armature:
            self.sync_auto_save = False
    except ValueError as error:
        self.sync_status = str(error)


def _resolve_armature_pick(settings, context):
    target = settings.live_link_armature
    if target is not None and target.type == 'MESH':
        armature = character_export.find_armature(context, target)
        if armature is None:
            raise ValueError('所选模型没有绑定蒙皮骨架。')
        # Replacing an ID pointer inside its own update callback corrupts users in 5.0.
        settings.live_link_armature = armature
    return settings.live_link_armature


def _session_items(_self, _context):
    return _session_enum_items


def _stream_snapshot():
    return (_static_transform_sender.snapshot() if _stream_model_type == 'static'
            else _live_link_sender.snapshot())


def _current_target(context, settings):
    _resolve_armature_pick(settings, context)
    active = context.object
    if active is not None:
        if active.type == 'MESH':
            armature = character_export.find_armature(context, active)
            if armature is None:
                return 'static', active
    if settings.live_link_armature is None and settings.sync_static_object is not None and (
            active is None or active.type not in ('MESH', 'ARMATURE')):
        return 'static', settings.sync_static_object
    armature = character_export.find_armature(context, settings.live_link_armature)
    if armature is None:
        raise ValueError('请选中一个静态网格、角色网格或骨架。')
    if not character_export.meshes_for(armature, context.scene):
        raise ValueError('所选骨架没有绑定蒙皮网格，请用吸管选择模型。')
    return 'skeletal', armature


def _stop_stream():
    global _stream_armature, _stream_skeleton, _stream_static_object, _stream_session_id, _stream_model_type, _stream_role_id, _stream_preparation_guard
    _live_link_sender.stop()
    _static_transform_sender.stop()
    _stream_armature, _stream_static_object, _stream_session_id = None, None, ''
    _stream_skeleton = None
    _stream_model_type, _stream_role_id = '', ''
    _stream_preparation_guard = None
    if bpy.app.timers.is_registered(_live_link_stream_timer):
        bpy.app.timers.unregister(_live_link_stream_timer)


def _on_session_changed(self, _context):
    global _auto_binding, _automatic_due
    _stop_stream()
    self.live_link_port = 0
    _auto_binding, _automatic_due = None, None
    if self.sync_auto_save:
        self.sync_auto_save = False
    self.sync_status = '请选择模型，然后同步到所选工程。'


def _on_auto_changed(self, _context):
    global _auto_binding, _automatic_due
    _automatic_due = None
    if not self.sync_auto_save:
        _auto_binding = None
        return
    try:
        model_type, obj = _current_target(_context or bpy.context, self)
        role = static_export.role_id(obj) if model_type == 'static' else character_export.role_id(obj)
        key = (self.sync_session, role)
        if key not in _synced_roles or _synced_roles[key].get('model_type', 'skeletal') != model_type:
            raise ValueError('请先成功同步此模型到当前 UE 工程。')
    except (ValueError, ReferenceError) as error:
        self.sync_auto_save = False
        self.sync_status = str(error)
        return
    _auto_binding = (key, obj)
    self.sync_status = '保存时更新已启用；只有网格、UV 或材质变化才重新导入。'


def _live_link_interval(settings):
    return 1.0 / max(1, int(settings.live_link_fps))


def _live_link_time_seconds(scene):
    rate = float(scene.render.fps) / max(float(scene.render.fps_base), 1e-9)
    return float(scene.frame_current_final) / rate


def _live_link_stream_timer():
    global _live_link_last_ui_error
    settings = _settings()
    if settings is None or not _stream_snapshot()['running']:
        return None
    # A successful import may reset a reused receiver's hierarchy and sequence.
    # Pause old frames until its response, then immediately resend the skeleton.
    if _pending is not None:
        return _live_link_interval(settings)
    try:
        if _stream_model_type == 'static':
            obj = _stream_static_object
            if obj is None or obj.type != 'MESH' or obj.find_armature() is not None:
                raise ValueError('静态模型目标不可用或已改为骨骼网格。')
            _static_transform_sender.send_transform(static_export.transform_data(obj, bpy.context.scene))
        else:
            armature = _stream_armature
            if armature is None or armature.type != 'ARMATURE':
                raise ValueError('Live Link 目标骨架不可用。')
            character_preprocess.validate_stream(armature, bpy.context.scene, _stream_preparation_guard)
            _live_link_sender.send_frame(_live_link_time_seconds(bpy.context.scene),
                live_link_pose.extract_unreal_local_transforms(armature, bpy.context.scene, _stream_skeleton))
        _live_link_last_ui_error = ''
    except Exception as error:
        _live_link_last_ui_error = str(error)
        _stop_stream()
        _tag_view3d_redraw()
        return None
    _tag_view3d_redraw()
    return _live_link_interval(settings)


def _ensure_live_link_timer(settings):
    if not bpy.app.timers.is_registered(_live_link_stream_timer):
        bpy.app.timers.register(_live_link_stream_timer,
                               first_interval=_live_link_interval(settings), persistent=True)


def _start_stream(settings, armature, port, session_id='', guard=None):
    global _live_link_last_ui_error, _stream_armature, _stream_skeleton, _stream_session_id, _stream_model_type, _stream_role_id, _stream_preparation_guard
    if port == 0:
        raise ValueError('尚未取得 UE 实际接收端口，请先同步模型，或填写 UE Source 显示的端口。')
    character_preprocess.validate_stream(armature, bpy.context.scene, guard)
    if (_live_link_sender.snapshot()['running'] and _stream_armature == armature and
            settings.live_link_port == port and _stream_session_id == session_id):
        _stream_preparation_guard = guard
        _stream_skeleton = live_link_pose.build_layout(armature)
        names, parents = _stream_skeleton['names'], _stream_skeleton['parents']
        _live_link_sender.send_skeleton(names, parents)
        _ensure_live_link_timer(settings)
        _live_link_last_ui_error = ''
        return
    previous_sequence = int(_live_link_sender.snapshot()['last_sequence'])
    _stop_stream()
    _stream_skeleton = live_link_pose.build_layout(armature)
    names, parents = _stream_skeleton['names'], _stream_skeleton['parents']
    settings.live_link_armature = armature
    settings.live_link_host = '127.0.0.1'
    settings.live_link_port = port
    settings.live_link_subject = LIVE_LINK_SUBJECT
    _live_link_sender.start(host='127.0.0.1', port=port,
                           subject=LIVE_LINK_SUBJECT, fps=settings.live_link_fps)
    _live_link_sender._sequence = previous_sequence
    _live_link_sender.send_skeleton(names, parents)
    _stream_armature, _stream_session_id = armature, session_id
    _stream_preparation_guard = guard
    _stream_model_type, _stream_role_id = 'skeletal', character_export.role_id(armature)
    _ensure_live_link_timer(settings)
    _live_link_last_ui_error = ''


def _start_static_stream(settings, obj, port, session_id):
    global _live_link_last_ui_error, _stream_static_object, _stream_session_id, _stream_model_type, _stream_role_id
    role = static_export.role_id(obj)
    current = _static_transform_sender.snapshot()
    if (current['running'] and _stream_static_object == obj and current['port'] == port and
            _stream_session_id == session_id and _stream_role_id == role):
        return
    _stop_stream()
    _static_transform_sender.start(port=port, session_id=session_id, role_id=role,
                                   fps=settings.live_link_fps)
    settings.live_link_port = port
    _stream_static_object, _stream_session_id = obj, session_id
    _stream_model_type, _stream_role_id = 'static', role
    _static_transform_sender.send_transform(static_export.transform_data(obj, bpy.context.scene))
    _ensure_live_link_timer(settings)
    _live_link_last_ui_error = ''


def _refresh_sessions(settings, *, automatic=False):
    global _sessions, _discovery_status, _discovery_details
    previous = settings.sync_session
    diagnostics = {}
    try:
        records = character_sync_client.discover_sessions(diagnostics=diagnostics)
        _discovery_status = (f'找到 {len(records)} 个在线 UE 工程，列表自动刷新。' if records else
                             '未发现在线工程，请等待 UE 加载完成并启用本版同步插件。')
        rejected = diagnostics.get('rejected', [])
        if rejected:
            _discovery_status += f' {len(rejected)} 条失效记录已忽略。'
        _discovery_details = '\n'.join([diagnostics.get('directory', ''), *dict.fromkeys(rejected)][:6])
    except (OSError, ValueError, TypeError, KeyError) as error:
        records = []
        _discovery_status = '工程发现失败：' + str(error)
        _discovery_details = str(character_sync_client.session_directory())
    _sessions = {record['session_id']: record for record in records}
    items = [('NONE', 'Select a UE Project', 'Online projects refresh automatically; select a sync target', 0, 0)]
    for record in records:
        label = f"{record.get('project_name', 'UE')} · UE {record.get('engine_version', '')} · {record.get('pid', '')}"
        # Blender stores enum numbers; stable values prevent list insertions changing the target.
        number = _session_enum_numbers.setdefault(record['session_id'], len(_session_enum_numbers) + 1)
        items.append((record['session_id'], label, record['project_file'], 0, number))
    desired = previous if previous in _sessions else 'NONE'
    if previous != desired:
        settings.sync_session = desired
    if items != _session_enum_items:
        _session_enum_items[:] = items
    if automatic:
        if previous != 'NONE' and previous not in _sessions:
            settings.sync_status = '所选 UE 工程会话已失效，发送已暂停；恢复在线后请重新选择。'
    else:
        settings.sync_status = _discovery_status


def _begin_sync(context, operation='sync', automatic=False, bound_target=None):
    global _pending
    settings = context.window_manager.blender_ue_live_link_settings
    if _pending is not None:
        raise ValueError('正在等待 UE 完成上一次同步。')
    session = character_sync_client.refresh_session(settings.sync_session)
    model_type, obj = bound_target if bound_target is not None else _current_target(context, settings)
    if model_type == 'static':
        if 'static_mesh_v1' not in session.get('capabilities', []):
            raise ValueError('目标 UE 插件尚不支持静态模型，请安装新版 UE 插件并重启工程。')
        inspected = static_export.inspect_static_mesh(context, obj)
        signature = inspected[1]
        role = static_export.role_id(obj)
        settings.sync_static_object = obj
    else:
        settings.live_link_armature = obj
        settings.sync_static_object = None
        prepared = character_preprocess.prepare_character(context, obj, enabled=settings.sync_uniform_scale)
        signature = prepared.signature
        role = character_export.role_id(obj)
    key = (session['session_id'], role)
    if automatic and session.get('active_role') not in ('', role):
        raise ValueError('UE 当前预览的是另一个模型，请手动同步后再启用自动更新。')
    if automatic and _synced_roles.get(key, {}).get('signature') == signature:
        settings.sync_status = '模型未变化，已跳过重新导入；变换或动作继续实时发送。'
        return False
    if operation == 'update' and key not in _synced_roles and session.get('active_role') != role:
        raise ValueError('此模型尚未同步到当前工程，请先点击“同步模型”。')
    settings.sync_status = '正在导出静态模型…' if model_type == 'static' else '正在导出角色…'
    request_id, payload = character_sync_client.allocate_payload(session)
    if model_type == 'static':
        metadata = static_export.export_static_mesh(context, obj, payload, request_id, inspected=inspected)
    else:
        metadata = prepared.export(payload, request_id)
        metadata['model_type'] = 'skeletal'
    metadata.update(operation=operation, asset_root=settings.sync_asset_root.strip(),
                    preview=True, automatic=bool(automatic), source_blend=bpy.data.filepath)
    # Validation can take longer than one heartbeat; do not publish to a closed/restarted editor.
    session = character_sync_client.refresh_session(settings.sync_session)
    if automatic and session.get('active_role') not in ('', role):
        raise ValueError('UE 当前预览目标已变化，自动更新已停止。')
    character_sync_client.publish_request(session, request_id, metadata)
    _pending = {'session': session, 'request_id': request_id, 'role_id': role,
                'armature': obj if model_type == 'skeletal' else None, 'object': obj,
                'model_type': model_type, 'signature': metadata['geometry_signature'],
                'started': time.monotonic(), 'warnings': metadata.get('warnings', []),
                'stream_guard': prepared.guard if model_type == 'skeletal' else None}
    settings.sync_status = '模型已发送，等待 UE 导入并配置连接…'
    settings.sync_details = '\n'.join(metadata.get('warnings', []))
    return True


def _finish_pending(settings):
    global _pending
    request = _pending
    if request is None:
        return
    try:
        response = character_sync_client.read_response(request['session'], request['request_id'], request['role_id'])
        if response is None:
            if time.monotonic() - request['started'] > character_sync_client.REQUEST_TIMEOUT:
                raise ValueError('等待 UE 超时，请检查 UE 日志。不要重复点击；先确认上一请求的结果。')
            return
        _pending = None
        notes = list(dict.fromkeys(request['warnings'] + list(response.get('warnings', []))))
        details = list(notes)
        if response.get('asset_path'):
            details.append('UE 资源：' + str(response['asset_path']))
        if response.get('backup_dir'):
            details.append('备份目录：' + str(response['backup_dir']))
        if response.get('status') == 'ok' and response.get('udp_port'):
            details.append('UE 接收地址：127.0.0.1:' + str(response['udp_port']))
        settings.sync_details = '\n'.join(details)
        if response['status'] != 'ok':
            raise ValueError(response.get('message', 'UE 同步未完成。'))
        model_type = request.get('model_type', 'skeletal')
        if response.get('model_type', 'skeletal') != model_type:
            raise ValueError('UE 返回的模型类型与当前请求不一致。')
        key = (request['session']['session_id'], request['role_id'])
        _synced_roles[key] = {'signature': request['signature'], 'asset_path': response.get('asset_path', ''),
                              'model_type': model_type, 'stream_guard': request.get('stream_guard')}
        if settings.sync_session == request['session']['session_id']:
            if model_type == 'static':
                _start_static_stream(settings, request['object'], int(response['static_udp_port']),
                                     request['session']['session_id'])
            else:
                _start_stream(settings, request['armature'], int(response['udp_port']), request['session']['session_id'],
                              guard=request.get('stream_guard'))
        settings.sync_status = response.get('message') or '模型同步完成，正在发送变换或动作。'
        if notes:
            settings.sync_status += '（有提示，请展开详细信息）'
    except (OSError, ValueError, TypeError, KeyError, ReferenceError) as error:
        _pending = None
        settings.sync_status = str(error)
        if settings.sync_auto_save:
            settings.sync_auto_save = False
            settings.sync_status += ' 自动更新已暂停。'


def _character_sync_timer():
    global _automatic_due, _next_session_poll
    settings = _settings()
    if settings is None:
        return 0.5
    try:
        _resolve_armature_pick(settings, bpy.context)
    except (ValueError, ReferenceError) as error:
        settings.live_link_armature = None
        settings.sync_status = str(error)
    _finish_pending(settings)
    if time.monotonic() >= _next_session_poll and _pending is None:
        _next_session_poll = time.monotonic() + 2.0
        _refresh_sessions(settings, automatic=True)
        session = _sessions.get(settings.sync_session)
        if (session and _stream_session_id == settings.sync_session and _stream_role_id and
                session.get('active_role') != _stream_role_id):
            _stop_stream()
            settings.sync_status = 'UE 预览目标已改变，发送已暂停，请重新同步模型。'
    if _automatic_due is not None and time.monotonic() >= _automatic_due and _pending is None:
        _automatic_due = None
        try:
            if settings.sync_auto_save and _auto_binding is not None:
                key, obj = _auto_binding
                model_type = _synced_roles.get(key, {}).get('model_type', 'skeletal')
                bound = settings.sync_static_object if model_type == 'static' else settings.live_link_armature
                if settings.sync_session != key[0] or bound != obj:
                    raise ValueError('同步目标已变化，请重新启用保存时更新。')
                _begin_sync(bpy.context, operation='update', automatic=True, bound_target=(model_type, obj))
        except Exception as error:
            settings.sync_auto_save = False
            settings.sync_status = f'自动更新已暂停：{error}'
    _tag_view3d_redraw()
    return 0.5


@persistent
def _on_save_post(_unused):
    global _automatic_due
    settings = _settings()
    if settings is not None and settings.sync_auto_save and _auto_binding is not None:
        _automatic_due = time.monotonic() + 1.0


_on_save_post._blender_ue_sync_handler = True


@persistent
def _on_load_pre(_unused):
    global _pending, _auto_binding, _automatic_due
    _stop_stream()
    _pending, _auto_binding, _automatic_due = None, None, None
    _synced_roles.clear()
    settings = _settings()
    if settings is not None:
        settings.live_link_armature = None
    if settings is not None and settings.sync_auto_save:
        settings.sync_auto_save = False


_on_load_pre._blender_ue_sync_handler = True


class BUEL_PG_bridge_settings(PropertyGroup):
    live_link_armature: PointerProperty(name='Skinned Armature', type=bpy.types.Object, poll=_poll_armature,
        translation_context=i18n.CONTEXT, update=_on_armature_changed,
        description='Use the eyedropper on a skinned mesh to select the armature bound by its Armature modifier')
    sync_static_object: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    live_link_host: StringProperty(name='UE Address', default='127.0.0.1', translation_context=i18n.CONTEXT)
    live_link_port: IntProperty(name='UE Port', default=0, min=0, max=65535, translation_context=i18n.CONTEXT,
                               description='0 means the actual receiver port assigned by UE is not available yet')
    live_link_subject: StringProperty(name='Subject', default=LIVE_LINK_SUBJECT, options={'HIDDEN'})
    live_link_fps: IntProperty(name='Stream FPS', default=30, min=1, max=120, translation_context=i18n.CONTEXT)
    sync_session: EnumProperty(name='UE Project', items=_session_items, update=_on_session_changed,
                              translation_context=i18n.CONTEXT)
    sync_asset_root: StringProperty(name='Asset Directory', default='/Game/BlenderLiveLink', translation_context=i18n.CONTEXT)
    sync_uniform_scale: BoolProperty(name='Normalize Scale Before Sync', default=True, translation_context=i18n.CONTEXT,
        description='Normalize fixed positive uniform armature scale on an export copy and validate animation; preserve the original character without saving the file')
    sync_auto_save: BoolProperty(name='Update Model on Save', default=False, update=_on_auto_changed,
        translation_context=i18n.CONTEXT,
        description='Enable after the first successful sync; reimport only when the model changes and pause automatically on failure')
    sync_status: StringProperty(default='打开 UE 工程，刷新并选择同步目标。')
    sync_details: StringProperty(default='')
    sync_show_details: BoolProperty(name='Details', default=False, translation_context=i18n.CONTEXT)
    sync_show_manual: BoolProperty(name='Manual Connection', default=False, translation_context=i18n.CONTEXT)


class BUEL_OT_refresh_projects(Operator):
    bl_idname = 'blender_ue_live_link.refresh_projects'
    bl_label = 'Refresh Projects'
    bl_description = 'Find local running UE projects with the model sync plugin enabled'
    bl_translation_context = i18n.CONTEXT

    def execute(self, context):
        try:
            _refresh_sessions(context.window_manager.blender_ue_live_link_settings)
        except (OSError, ValueError) as error:
            self.report({'ERROR'}, i18n.message(str(error)))
            return {'CANCELLED'}
        return {'FINISHED'}


class BUEL_OT_sync_character(Operator):
    bl_idname = 'blender_ue_live_link.sync_character'
    bl_label = 'Sync Model'
    bl_description = 'Send the active static mesh or skinned character, create dedicated assets, and configure the preview'
    bl_translation_context = i18n.CONTEXT

    def execute(self, context):
        try:
            _begin_sync(context, operation='sync')
        except Exception as error:
            context.window_manager.blender_ue_live_link_settings.sync_status = str(error)
            self.report({'ERROR'}, i18n.message(str(error)))
            return {'CANCELLED'}
        return {'FINISHED'}


class BUEL_OT_update_character(Operator):
    bl_idname = 'blender_ue_live_link.update_character'
    bl_label = 'Update Model'
    bl_description = 'Update the current model assets while preserving material assignments in UE'
    bl_translation_context = i18n.CONTEXT

    def execute(self, context):
        try:
            _begin_sync(context, operation='update')
        except Exception as error:
            context.window_manager.blender_ue_live_link_settings.sync_status = str(error)
            self.report({'ERROR'}, i18n.message(str(error)))
            return {'CANCELLED'}
        return {'FINISHED'}


class BUEL_OT_start_live_link(Operator):
    bl_idname = 'blender_ue_live_link.start_live_link'
    bl_label = 'Start Live Link'
    bl_description = 'Stream static mesh transforms or skeletal poses without reimporting model assets'
    bl_translation_context = i18n.CONTEXT

    def execute(self, context):
        settings = context.window_manager.blender_ue_live_link_settings
        try:
            model_type, obj = _current_target(context, settings)
            if model_type == 'static':
                if settings.sync_session == 'NONE':
                    raise ValueError('静态模型需要选择新版 UE 工程并先点击“同步模型”。')
                session = character_sync_client.refresh_session(settings.sync_session)
                role = static_export.role_id(obj)
                if ((session['session_id'], role) not in _synced_roles or
                        session.get('active_role') != role or
                        'static_mesh_v1' not in session.get('capabilities', [])):
                    raise ValueError('请先将此静态模型同步到当前 UE 工程。')
                _start_static_stream(settings, obj, int(session['static_udp_port']), session['session_id'])
            else:
                port, session_id = int(settings.live_link_port), ''
                guard = None
                if settings.sync_session != 'NONE':
                    session = character_sync_client.refresh_session(settings.sync_session)
                    role = character_export.role_id(obj)
                    if (session['session_id'], role) not in _synced_roles:
                        raise ValueError('请先点击“同步模型”建立本次连接。')
                    if session.get('active_role') != role:
                        raise ValueError('请先将此角色同步到所选 UE 工程。')
                    port, session_id = int(session['udp_port']), session['session_id']
                    guard = _synced_roles[(session_id, role)].get('stream_guard')
                _start_stream(settings, obj, port, session_id, guard=guard)
        except Exception as error:
            _stop_stream()
            settings.sync_status = str(error)
            self.report({'ERROR'}, i18n.message(str(error)))
            return {'CANCELLED'}
        settings.sync_status = '模型变换或动作发送已启动。'
        return {'FINISHED'}


class BUEL_OT_stop_live_link(Operator):
    bl_idname = 'blender_ue_live_link.stop_live_link'
    bl_label = 'Stop Live Link'
    bl_description = 'Stop streaming model transforms or skeletal poses'
    bl_translation_context = i18n.CONTEXT

    def execute(self, _context):
        _stop_stream()
        return {'FINISHED'}


class BUEL_PT_bridge(Panel):
    bl_label = 'Blender UE Live Link'
    bl_idname = 'BUEL_PT_bridge'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'UE Live Link'

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.blender_ue_live_link_settings
        running = _stream_snapshot()['running']
        target = layout.column()
        target.enabled = _pending is None
        projects = target.row(align=True)
        projects.prop(settings, 'sync_session')
        projects.operator('blender_ue_live_link.refresh_projects', text='', icon='FILE_REFRESH')
        for line in _wrap_text(i18n.message(_discovery_status), 30):
            target.label(text=line, translate=False)
        active = context.object
        if active is not None and active.type == 'MESH' and active.find_armature() is None:
            target.label(text=i18n.iface('静态模型：') + active.name, icon='MESH_DATA', translate=False)
        else:
            target.prop(settings, 'live_link_armature')
            target.prop(settings, 'sync_uniform_scale')
            if settings.sync_uniform_scale:
                for line in _wrap_text(i18n.iface('整理导出副本，保留原角色与动画。'), 34):
                    target.label(text=line, translate=False)
        buttons = target.row(align=True)
        buttons.enabled = settings.sync_session in _sessions
        buttons.operator('blender_ue_live_link.sync_character', icon='EXPORT')
        buttons.operator('blender_ue_live_link.update_character', icon='FILE_REFRESH')
        target.prop(settings, 'sync_auto_save')
        status = layout.box()
        for line in _wrap_text(i18n.message(settings.sync_status), 30):
            status.label(text=line, translate=False)
        status.label(text=i18n.iface('同步：正在发送' if running else '同步：已停止'), translate=False)
        session = _sessions.get(settings.sync_session)
        if session:
            # This number is historical; do not label it as proof of a current connection.
            status.label(text=i18n.message(f"UE 已接收 {session.get('accepted_frames', 0)} 帧"), translate=False)
        elif settings.sync_session != 'NONE':
            for line in _wrap_text(i18n.iface('UE 工程未响应，请刷新。'), 30):
                status.label(text=line, icon='ERROR', translate=False)
        layout.prop(settings, 'sync_show_details', icon='TRIA_DOWN' if settings.sync_show_details else 'TRIA_RIGHT', emboss=False)
        if settings.sync_show_details:
            details = layout.box()
            for line in _discovery_details.splitlines():
                for wrapped in _wrap_text(i18n.message(line), 34):
                    details.label(text=wrapped, translate=False)
            details.prop(settings, 'sync_asset_root')
            details.prop(settings, 'live_link_fps')
            if session:
                for line in _wrap_text(session['project_file'], 34):
                    details.label(text=line, translate=False)
            for line in settings.sync_details.splitlines():
                for wrapped in _wrap_text(i18n.message(line), 34):
                    details.label(text=wrapped, translate=False)
            for tip in ('同时预览一个模型；静态网格一次发送一个活动对象。',
                        '静态模型支持正数缩放；剪切和镜像变换会停止发送。',
                        '支持基础材质与贴图；保留 UE 中替换的材质。',
                        '统一缩放支持固定正数等比缩放；动作验证失败会停止同步。'):
                for line in _wrap_text(i18n.iface(tip), 34):
                    details.label(text=line, translate=False)
        controls = layout.row(align=True)
        start = controls.row(align=True)
        start.enabled = not running and _pending is None
        start.operator('blender_ue_live_link.start_live_link', icon='PLAY')
        stop = controls.row(align=True)
        stop.enabled = running
        stop.operator('blender_ue_live_link.stop_live_link', icon='PAUSE')
        layout.prop(settings, 'sync_show_manual', icon='TRIA_DOWN' if settings.sync_show_manual else 'TRIA_RIGHT', emboss=False)
        if settings.sync_show_manual:
            manual = layout.box()
            manual.enabled = not running and settings.sync_session == 'NONE'
            for line in _wrap_text(i18n.iface('旧版 UE 仅支持骨骼姿态，需手动 Source 和动画蓝图。'), 34):
                manual.label(text=line, translate=False)
            manual.prop(settings, 'live_link_port')
        error = _live_link_last_ui_error or _stream_snapshot()['last_error']
        if error:
            for line in _wrap_text(i18n.message(error), 30):
                layout.label(text=line, icon='ERROR', translate=False)


def _wrap_text(text, width):
    return textwrap.wrap(text, width=width, break_on_hyphens=False,
                         replace_whitespace=False, drop_whitespace=True) or ['']


CLASSES = (BUEL_PG_bridge_settings, BUEL_OT_refresh_projects,
           BUEL_OT_sync_character, BUEL_OT_update_character,
           BUEL_OT_start_live_link, BUEL_OT_stop_live_link, BUEL_PT_bridge)


def register():
    i18n.register()
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.blender_ue_live_link_settings = PointerProperty(type=BUEL_PG_bridge_settings)
    if _on_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_on_save_post)
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)
    if not bpy.app.timers.is_registered(_character_sync_timer):
        bpy.app.timers.register(_character_sync_timer, first_interval=0.5, persistent=True)


def unregister():
    global _pending, _auto_binding, _automatic_due
    _stop_stream()
    _pending, _auto_binding, _automatic_due = None, None, None
    if bpy.app.timers.is_registered(_character_sync_timer):
        bpy.app.timers.unregister(_character_sync_timer)
    if _on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_on_save_post)
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    if hasattr(bpy.types.WindowManager, 'blender_ue_live_link_settings'):
        del bpy.types.WindowManager.blender_ue_live_link_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    i18n.unregister()
