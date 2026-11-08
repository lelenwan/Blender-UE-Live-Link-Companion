"""Export only the chosen skinned character; restore all temporary scene state."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

import bpy

from . import character_sync_client as exchange
from . import api_compat, live_link_pose, live_link_protocol

ROLE_ID_PROPERTY = 'blender_ue_live_link_role_id'
ROLE_OWNER_PROPERTY = 'blender_ue_live_link_role_owner'


def find_armature(context, explicit=None):
    active = explicit if explicit is not None else context.object
    if active is not None and active.type == 'ARMATURE':
        return active
    if active is not None and active.type == 'MESH':
        bound = {m.object for m in active.modifiers if m.type == 'ARMATURE' and m.object is not None}
        if len(bound) > 1:
            raise ValueError('模型绑定了多套骨架，请先保留单一蒙皮骨架。')
        return next(iter(bound), None)
    return None


def meshes_for(armature, scene):
    return sorted((obj for obj in scene.objects if obj.type == 'MESH' and
                   any(mod.type == 'ARMATURE' and mod.object == armature for mod in obj.modifiers)),
                  key=lambda obj: obj.name)


def role_id(armature):
    value = armature.get(ROLE_ID_PROPERTY, '')
    if not exchange.HEX_ID.fullmatch(str(value)):
        value = uuid.uuid4().hex
        armature[ROLE_ID_PROPERTY] = value
        armature[ROLE_OWNER_PROPERTY] = armature.name
    collisions = [obj for obj in bpy.data.objects if obj.type in ('ARMATURE', 'MESH') and
                  obj.get(ROLE_ID_PROPERTY) == value]
    if len(collisions) > 1:
        owners = [obj for obj in collisions if obj.get(ROLE_OWNER_PROPERTY) == obj.name]
        original = owners[0] if len(owners) == 1 else None
        # Object duplication copies custom properties. Keep the identifiable
        # original and give every copy its own identity. If ownership is
        # ambiguous after renames, allocate fresh identities rather than risk
        # replacing a different character in UE.
        for obj in collisions:
            if obj != original:
                obj[ROLE_ID_PROPERTY] = uuid.uuid4().hex
                obj[ROLE_OWNER_PROPERTY] = obj.name
        value = armature[ROLE_ID_PROPERTY]
    armature[ROLE_OWNER_PROPERTY] = armature.name
    return value


def _rounded(values):
    return [round(float(value), 7) for value in values]


def _feed(digest, value):
    digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                             allow_nan=False).encode('utf-8'))
    digest.update(b'\n')


def skeleton_data(armature, scene):
    layout = live_link_pose.build_layout(armature)
    names, parents, sources = layout['names'], layout['parents'], layout['source_names']
    if parents.count(-1) != 1:
        raise ValueError('角色需要且只能有一根根骨骼；请先整理骨架层级。')
    if not names:
        raise ValueError('所选骨架没有骨骼。')
    transforms = []
    digest = hashlib.sha256()
    _feed(digest, [names, parents, float(scene.unit_settings.scale_length)])
    for name in names:
        index = len(transforms)
        matrix = live_link_pose.source_matrix(armature, sources[index], rest=True)
        parent = parents[index]
        matrix = (armature.matrix_world @ matrix if parent < 0 else
                  live_link_pose.source_matrix(armature, sources[parent], rest=True).inverted_safe() @ matrix)
        _feed(digest, [_rounded(row) for row in matrix])
        transforms.append(list(live_link_pose._to_unreal_transform(
            matrix, float(scene.unit_settings.scale_length) * 100.0)))
    return {'names': names, 'parents': parents, 'rest_signature': digest.hexdigest(),
            'rest_transforms': transforms}


def geometry_signature(armature, meshes, context):
    digest = hashlib.sha256()
    _feed(digest, skeleton_data(armature, context.scene)['rest_signature'])
    original_pose = armature.data.pose_position
    try:
        armature.data.pose_position = 'REST'
        context.view_layer.update()
        graph = context.evaluated_depsgraph_get()
        for obj in meshes:
            _feed(digest, obj.name)
            _feed(digest, [_rounded(row) for row in obj.matrix_world])
            data = obj.data
            group_names = {group.index: group.name for group in obj.vertex_groups}
            for vertex in data.vertices:
                _feed(digest, [vertex.index, _rounded(vertex.co),
                               [(group_names.get(group.group, ''), round(group.weight, 7))
                                for group in vertex.groups]])
            for polygon in data.polygons:
                _feed(digest, [list(polygon.vertices), polygon.material_index, polygon.use_smooth])
            for name, coordinates in api_compat.uv_layers(data):
                _feed(digest, name)
                for coordinate in coordinates:
                    _feed(digest, _rounded(coordinate))
            # Evaluating at rest catches modifier/shape changes while bone poses
            # and animation frame changes leave the signature untouched.
            evaluated = obj.evaluated_get(graph)
            mesh = evaluated.to_mesh()
            try:
                for vertex in mesh.vertices:
                    _feed(digest, _rounded(vertex.co))
                for polygon in mesh.polygons:
                    _feed(digest, list(polygon.vertices))
            finally:
                evaluated.to_mesh_clear()
            for slot in obj.material_slots:
                material = slot.material
                _feed(digest, material.name if material else '')
                if material:
                    values, image, _warnings = _material_values(material)
                    _feed(digest, values)
                    if image is not None:
                        source = Path(bpy.path.abspath(image.filepath))
                        _feed(digest, [image.name, image.source, str(source), bool(image.is_dirty)])
                        if image.packed_file is not None:
                            _feed(digest, hashlib.sha256(bytes(image.packed_file.data)).hexdigest())
                        elif source.is_file():
                            stat = source.stat()
                            _feed(digest, [stat.st_size, stat.st_mtime_ns])
    finally:
        armature.data.pose_position = original_pose
        context.view_layer.update()
    return digest.hexdigest()


def _material_values(material):
    values = {'name': material.name, 'base_color': list(material.diffuse_color),
              'metallic': float(material.metallic), 'roughness': float(material.roughness)}
    image = None
    warnings = []
    if material.use_nodes and material.node_tree:
        outputs = [node for node in material.node_tree.nodes if node.type == 'OUTPUT_MATERIAL' and node.is_active_output]
        links = outputs[0].inputs['Surface'].links if outputs else []
        principled = links[0].from_node if links else None
        if principled is None or principled.type != 'BSDF_PRINCIPLED':
            warnings.append(f'材质“{material.name}”不是直接连接的 Principled BSDF，仅传基础颜色。')
        else:
            values['base_color'] = list(principled.inputs['Base Color'].default_value)
            values['base_color'][3] = float(principled.inputs['Alpha'].default_value)
            values['metallic'] = float(principled.inputs['Metallic'].default_value)
            values['roughness'] = float(principled.inputs['Roughness'].default_value)
            color_links = principled.inputs['Base Color'].links
            if color_links:
                node = color_links[0].from_node
                if (node.type == 'TEX_IMAGE' and node.image and
                        color_links[0].from_socket.name == 'Color'):
                    image = node.image
                    # A linked input ignores its stored socket default in Blender.
                    # UE multiplies texture * BaseColor, so use a neutral factor.
                    values['base_color'] = [1.0, 1.0, 1.0, values['base_color'][3]]
                    if node.inputs['Vector'].is_linked:
                        warnings.append(f'材质“{material.name}”使用自定义贴图坐标，UE 基础材质使用第一套 UV。')
                else:
                    warnings.append(f'材质“{material.name}”的颜色节点需要烘焙，暂传基础颜色。')
            if principled.inputs['Alpha'].is_linked:
                warnings.append(f'材质“{material.name}”的透明度节点尚未转换。')
            if principled.inputs['Metallic'].is_linked or principled.inputs['Roughness'].is_linked:
                warnings.append(f'材质“{material.name}”的金属度或粗糙度贴图尚未转换。')
    return values, image, warnings


def export_materials(meshes, payload_dir, request_id):
    materials, warnings, seen = [], [], set()
    for obj in meshes:
        for material_slot in obj.material_slots:
            material = material_slot.material
            if material is None or material.name in seen:
                continue
            seen.add(material.name)
            values, image, notes = _material_values(material)
            values['slot'] = len(materials)
            warnings.extend(notes)
            if image is not None:
                try:
                    if image.source != 'FILE':
                        description = {'TILED': 'UDIM', 'MOVIE': '视频', 'GENERATED': '生成图像',
                                       'SEQUENCE': '图像序列'}.get(image.source, image.source)
                        raise ValueError(f'当前不支持{description}贴图，请先转换为普通 PNG/JPG 文件')
                    if image.is_dirty:
                        warnings.append(f'贴图“{image.name}”有未保存或未重新打包的像素修改，本次使用已保存或已打包的数据。')
                    encoded = None
                    if image.packed_file is not None:
                        encoded = bytes(image.packed_file.data)
                        if encoded.startswith(b'\x89PNG\r\n\x1a\n'):
                            suffix = '.png'
                        elif encoded.startswith(b'\xff\xd8\xff'):
                            suffix = '.jpg'
                        else:
                            raise ValueError('打包内容不是普通 PNG/JPG 编码，暂未传输')
                        if not 0 < len(encoded) <= 256 * 1024 * 1024:
                            raise ValueError('打包贴图为空或超过 256 MiB')
                    else:
                        source = Path(bpy.path.abspath(image.filepath)).resolve()
                        suffix = source.suffix.lower()
                        if suffix not in ('.png', '.jpg', '.jpeg'):
                            raise ValueError('当前只传输 PNG/JPG 文件')
                        if not source.is_file():
                            raise ValueError('文件不存在')
                        if not 0 < source.stat().st_size <= 256 * 1024 * 1024:
                            raise ValueError('贴图为空或超过 256 MiB')
                    destination = payload_dir / 'textures' / (str(values['slot']) + suffix)
                    destination.parent.mkdir(exist_ok=True)
                    if encoded is not None:
                        destination.write_bytes(encoded)
                    else:
                        shutil.copy2(source, destination)
                    values['texture'] = 'payloads/' + request_id + '/textures/' + destination.name
                    values['texture_sha256'] = exchange.file_sha256(destination)
                except (OSError, ValueError) as error:
                    warnings.append(f'贴图“{image.name}”未传输：{error}')
            materials.append(values)
    return materials, warnings


def inspect_character(context, armature):
    if armature is None or armature.type != 'ARMATURE':
        raise ValueError('请选中角色网格或指定目标骨架。')
    if armature.mode == 'EDIT':
        raise ValueError('请退出骨架编辑模式后再同步。')
    if armature.library is not None or armature.override_library is not None:
        raise ValueError('请先将角色设为本地可编辑对象。')
    if any(abs(float(value) - 1.0) > 1e-5 for value in armature.scale):
        raise ValueError('骨架对象缩放须为 1；请先应用缩放，避免 UE 模型与动作比例不同。')
    world = armature.matrix_world.to_3x3()
    axes = [world.col[index] for index in range(3)]
    if (world.determinant() <= 0 or any(abs(axis.length - 1.0) > 1e-5 for axis in axes) or
            any(abs(axes[a].dot(axes[b])) > 1e-5 for a, b in ((0, 1), (0, 2), (1, 2)))):
        raise ValueError('骨架的父级引入了缩放、镜像或剪切；请先应用父级变换，保持骨架世界缩放为 1。')
    meshes = meshes_for(armature, context.scene)
    if not meshes:
        raise ValueError('所选骨架没有绑定网格；请检查 Armature 修改器。')
    for mesh in meshes:
        if mesh.mode == 'EDIT':
            raise ValueError(f'请退出网格“{mesh.name}”的编辑模式后再同步。')
        if mesh.hide_get() or mesh.hide_viewport or mesh.hide_select:
            raise ValueError(f'网格“{mesh.name}”被隐藏或禁止选择，请先显示后再同步。')
        if mesh.data.shape_keys and len(mesh.data.shape_keys.key_blocks) > 1:
            raise ValueError(f'网格“{mesh.name}”含形态键；当前角色同步暂不支持形态键，请使用独立副本验证。')
    skeleton = skeleton_data(armature, context.scene)
    try:
        sequence = 9007199254740991  # Reserve room for a long-running sequence counter.
        live_link_protocol.encode_skeleton('BlenderUELiveLink', sequence, skeleton['names'], skeleton['parents'])
        live_link_protocol.encode_frame('BlenderUELiveLink', sequence, 0.0, skeleton['rest_transforms'])
        live_link_protocol.encode_frame('BlenderUELiveLink', sequence, 0.0,
            live_link_pose.extract_unreal_local_transforms(armature, context.scene))
    except live_link_protocol.ProtocolError as error:
        raise ValueError(f'此骨架无法通过当前 Live Link 协议发送（单包上限 60 KiB），请精简骨骼后重试：{error}') from error
    signature = geometry_signature(armature, meshes, context)
    return meshes, skeleton, signature


def export_character(context, armature, payload_dir, request_id, inspected=None):
    meshes, skeleton, signature = inspected if inspected is not None else inspect_character(context, armature)
    payload_dir = Path(payload_dir)
    materials, warnings = export_materials(meshes, payload_dir, request_id)
    previous_active = context.view_layer.objects.active
    previous_selected = list(context.selected_objects)
    previous_mode = previous_active.mode if previous_active is not None else 'OBJECT'
    previous_pose = armature.data.pose_position
    previous_name = armature.name
    collision = bpy.data.objects.get('Armature')
    collision_name = collision.name if collision is not None else None
    renamed_collision = collision is not None and collision != armature
    try:
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for obj in [armature, *meshes]:
            obj.select_set(True)
        context.view_layer.objects.active = armature
        armature.data.pose_position = 'REST'
        if renamed_collision:
            collision.name = 'UE_EXPORT_' + uuid.uuid4().hex
        armature.name = 'Armature'
        context.view_layer.update()
        result = api_compat.export_fbx(payload_dir / 'character.fbx', model_type='skeletal')
        if result != {'FINISHED'}:
            raise ValueError('FBX 导出未完成。')
    finally:
        armature.name = previous_name
        if renamed_collision:
            collision.name = collision_name
        armature.data.pose_position = previous_pose
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        for obj in previous_selected:
            obj.select_set(True)
        context.view_layer.objects.active = previous_active
        context.view_layer.update()
        if previous_active is not None and previous_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=previous_mode)
    return {'role_id': role_id(armature), 'role_name': previous_name,
            'skeleton': skeleton, 'geometry_signature': signature,
            'materials': materials, 'meshes': [obj.name for obj in meshes],
            'warnings': warnings}
