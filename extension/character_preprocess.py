"""Prepare an isolated, unit-scale export rig without changing the source character.

The exported FBX uses a normalized rest skeleton. Its request deliberately retains
the ORIGINAL source rest transforms: the existing UE retargeter uses those with
the unchanged original live-pose stream to reconstruct the imported bind frame.
"""
import math
from contextlib import contextmanager

import bpy
import numpy as np
from mathutils import Matrix

from . import character_export as export
from . import live_link_pose, live_link_protocol

POSITION_TOLERANCE_METERS = 0.0001
MAX_VALIDATION_SAMPLES = 10001


def _action_curves(obj):
    animation = obj.animation_data
    action = animation.action if animation else None
    if action is None:
        return []
    found = []
    slot = getattr(animation, 'action_slot_handle', None)
    for layer in getattr(action, 'layers', ()):
        for strip in layer.strips:
            for bag in getattr(strip, 'channelbags', ()):
                if slot is None or bag.slot_handle == slot:
                    found.extend(bag.fcurves)
    if not found and hasattr(action, 'fcurves'):
        found.extend(action.fcurves)
    return found


def _positive_uniform(values, label):
    values = [float(v) for v in values]
    if any(not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError(label + '含零值、负值或无效数值，不能自动统一。')
    factor = sum(values) / 3.0
    if max(abs(v - factor) for v in values) > max(1e-7, abs(factor) * 1e-5):
        raise ValueError(label + '不是等比缩放；本版只自动处理固定正数等比缩放。')
    return factor


def _world_factor(armature):
    world = armature.matrix_world
    if any(not math.isfinite(float(v)) for row in world for v in row):
        raise ValueError('骨架世界变换含无效数值。')
    axes = [world.to_3x3().col[i] for i in range(3)]
    factor = _positive_uniform([v.length for v in axes], '骨架世界缩放')
    if world.to_3x3().determinant() <= 0 or any(
            abs(axes[a].normalized().dot(axes[b].normalized())) > 1e-5
            for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError('骨架世界变换含镜像或剪切，不能自动统一。')
    return factor


def _material_repairs(meshes):
    repairs = {}
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or material in repairs:
                continue
            values, _image, _warnings = export._material_values(material)
            fields = []
            for field in ('metallic', 'roughness'):
                value = values[field]
                if not math.isfinite(value):
                    raise ValueError(f'材质“{material.name}”的{field}不是有效数值。')
                if not 0.0 <= value <= 1.0:
                    outputs = [n for n in material.node_tree.nodes
                               if n.type == 'OUTPUT_MATERIAL' and n.is_active_output] if material.node_tree else []
                    links = outputs[0].inputs['Surface'].links if outputs else []
                    node = links[0].from_node if links else None
                    socket = 'Metallic' if field == 'metallic' else 'Roughness'
                    if node is None or node.type != 'BSDF_PRINCIPLED' or node.inputs[socket].is_linked:
                        raise ValueError(f'材质“{material.name}”的{socket}超范围且不是可直接整理的常量。')
                    fields.append((node.name, socket, float(value), min(1.0, max(0.0, float(value)))))
            if fields:
                repairs[material] = fields
    return repairs


def _samples(armature, scene, evaluated=False):
    curves = _action_curves(armature)
    if not curves and not evaluated:
        return [float(scene.frame_current_final)]
    keys = {float(k.co.x) for curve in curves for k in curve.keyframe_points}
    keys.update(float(k.co.x) for curve in curves for k in curve.sampled_points)
    if not keys and not evaluated:
        return [float(scene.frame_current_final)]
    start = min(float(scene.frame_start), min(keys, default=scene.frame_start), float(scene.frame_current_final))
    end = max(float(scene.frame_end), max(keys, default=scene.frame_end), float(scene.frame_current_final))
    first, last = math.floor(start * 2), math.ceil(end * 2)
    if last - first + 1 + len(keys) > MAX_VALIDATION_SAMPLES * 2:
        raise ValueError('当前动作范围过长，统一缩放需要分段验证；请先整理为较短的烘焙动作。')
    frames = sorted({i * 0.5 for i in range(first, last + 1)} | keys |
                    {float(scene.frame_current_final)})
    if len(frames) > MAX_VALIDATION_SAMPLES:
        raise ValueError('统一缩放的动作采样数超出上限，请先整理为较短的烘焙动作。')
    return frames


def _points(obj, graph):
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(depsgraph=graph)
    try:
        coordinates = np.empty((len(mesh.vertices), 3), dtype=np.float32)
        mesh.vertices.foreach_get('co', coordinates.ravel())
        matrix = np.asarray(evaluated.matrix_world, dtype=np.float64)
        return coordinates @ matrix[:3, :3].T + matrix[:3, 3]
    finally:
        evaluated.to_mesh_clear()


def validate_stream(armature, scene, guard):
    """Reject changes which would invalidate the exported normalization."""
    if guard is None:
        return
    if armature.mode == 'EDIT' or scene != guard['scene'] or armature.data != guard['data']:
        raise ValueError('统一缩放的角色或骨架已改变，请重新同步模型。')
    if armature.parent != guard['parent']:
        raise ValueError('骨架父级已改变，请重新同步模型。')
    if abs(float(scene.unit_settings.scale_length) - guard['unit']) > 1e-8:
        raise ValueError('场景单位已改变，请重新同步模型。')
    factor = _world_factor(armature)
    if abs(factor - guard['factor']) > max(1e-7, guard['factor'] * 1e-5):
        raise ValueError('骨架对象缩放已改变，请重新统一缩放并同步模型。')
    if len(armature.data.bones) != len(guard['bones']):
        raise ValueError('骨架结构已改变，请重新同步模型。')
    for name, parent, matrix in guard['bones']:
        bone = armature.data.bones.get(name)
        if bone is None or (bone.parent.name if bone.parent else None) != parent or bone.matrix_local != matrix:
            raise ValueError('骨架参考姿态已改变，请重新同步模型。')


class CharacterPreparation:
    def __init__(self, context, armature, enabled=True):
        self.context, self.source, self.scene = context, armature, context.scene
        self.guard = None
        self.report = None
        self.inspected = None
        self.isolated = False
        if armature is None or armature.type != 'ARMATURE':
            raise ValueError('请选中角色网格或骨架。')
        local_factor = _positive_uniform(armature.scale, '骨架对象缩放')
        _positive_uniform(armature.delta_scale, '骨架增量缩放')
        factor = _world_factor(armature)
        if not enabled and (abs(local_factor - 1) > 1e-5 or abs(factor - 1) > 1e-5):
            # Preserve the existing explicit opt-out of scale normalization.
            export.inspect_character(context, armature)
        self.meshes = export.meshes_for(armature, self.scene)
        repairs = _material_repairs(self.meshes)
        self.layout = live_link_pose.build_layout(armature)
        names, parents = self.layout['names'], self.layout['parents']
        animation = armature.animation_data
        evaluated = bool(armature.constraints or any(p.constraints for p in armature.pose.bones) or
                         (animation and (animation.drivers or animation.nla_tracks)) or
                         (armature.data.animation_data and armature.data.animation_data.drivers))
        needs = (abs(local_factor - 1) > 1e-5 or abs(factor - 1) > 1e-5 or
                 armature.hide_get() or armature.hide_render or bool(repairs) or evaluated or
                 set(names) != {b.name for b in armature.data.bones} or
                 any(obj.data.shape_keys for obj in self.meshes))
        if not needs:
            self.inspected = export.inspect_character(context, armature)
            self.signature = self.inspected[2]
            return
        if armature.mode != 'OBJECT' and armature.mode != 'POSE':
            raise ValueError('请退出骨架编辑模式后再统一缩放。')
        if armature.library is not None or armature.override_library is not None:
            raise ValueError('统一缩放需要本地可编辑骨架。')
        if armature.hide_viewport:
            raise ValueError('骨架已禁用视口求值，请先启用骨架再统一缩放。')
        if armature.data.pose_position != 'POSE':
            raise ValueError('请将骨架切到“姿态位置”后再统一缩放。')
        if abs(factor - 1) > 1e-5 and armature.parent is not None:
            raise ValueError('本版暂不自动整理带父级的非单位骨架，请先在独立副本中整理父级。')
        for curve in _action_curves(armature):
            if curve.data_path not in ('scale', 'delta_scale'):
                continue
            expected = float(getattr(armature, curve.data_path)[curve.array_index])
            bezier = any(k.interpolation == 'BEZIER' for k in curve.keyframe_points)
            if curve.modifiers or any(abs(k.co.y - expected) > 1e-7
                                     for k in curve.keyframe_points) or (bezier and any(
                                     abs(k.handle_left.y - expected) > 1e-7 or
                                     abs(k.handle_right.y - expected) > 1e-7
                                     for k in curve.keyframe_points)) or any(
                                     abs(k.co.y - expected) > 1e-7 for k in curve.sampled_points):
                raise ValueError('骨架对象的缩放随动画变化，本版只支持固定等比缩放。')
        if not self.meshes:
            raise ValueError('所选骨架没有绑定网格，请检查 Armature 修改器。')
        for obj in self.meshes:
            if obj.mode == 'EDIT' or obj.hide_get() or obj.hide_viewport or obj.hide_select:
                raise ValueError(f'请先退出编辑模式并显示可选择的网格“{obj.name}”。')
            if not obj.data.vertices:
                raise ValueError(f'网格“{obj.name}”为空，不能统一缩放。')
            if obj.data.shape_keys and any(k != obj.data.shape_keys.reference_key and abs(k.value) > 1e-7
                                           for k in obj.data.shape_keys.key_blocks):
                raise ValueError(f'网格“{obj.name}”的形态键不是零值；当前只同步骨骼动作，请先归零表情后同步。')
            if obj.constraints or obj.animation_data:
                raise ValueError(f'网格“{obj.name}”含对象动画或约束，请先在副本中烘焙。')
            for modifier in obj.modifiers:
                if modifier.type == 'ARMATURE' and (not modifier.show_viewport or not modifier.show_render or
                        modifier.use_deform_preserve_volume or not modifier.use_vertex_groups or modifier.use_bone_envelopes):
                    raise ValueError(f'网格“{obj.name}”需要已启用的普通顶点组蒙皮；本版不自动转换包络或双四元数蒙皮。')
            if any(m.type == 'ARMATURE' and m.object != armature for m in obj.modifiers):
                raise ValueError(f'网格“{obj.name}”由多套骨架驱动，不能自动统一缩放。')
        unit = float(self.scene.unit_settings.scale_length)
        if not math.isfinite(unit) or unit <= 0:
            raise ValueError('场景单位比例无效。')
        self.isolated = True
        self.factor, self.unit, self.repairs = factor, unit, repairs
        self.skeleton = export.skeleton_data(armature, self.scene)
        if len({name.casefold() for name in self.skeleton['names']}) != len(self.skeleton['names']):
            raise ValueError('骨骼名称在 UE 中存在大小写冲突，请先整理名称。')
        self.signature = export.geometry_signature(armature, self.meshes, context)
        self.frames = _samples(armature, self.scene, evaluated=evaluated)
        self.names = self.skeleton['names']
        self.rest = {name: np.asarray(live_link_pose.source_matrix(armature, source, rest=True), dtype=np.float64)
                     for name, source in zip(self.names, self.layout['source_names'])}
        self.rest_inverse = {name: np.linalg.inv(matrix) for name, matrix in self.rest.items()}
        self.guard = {
            'scene': self.scene, 'data': armature.data, 'parent': armature.parent,
            'unit': unit, 'factor': factor,
            'bones': [(b.name, b.parent.name if b.parent else None, b.matrix_local.copy())
                      for b in armature.data.bones],
        }

    @contextmanager
    def _copies(self):
        context = self.context
        old_frame, old_sub = self.scene.frame_current, self.scene.frame_subframe
        old_active = context.view_layer.objects.active
        old_mode = old_active.mode if old_active is not None else 'OBJECT'
        old_selected = list(context.selected_objects)
        objects, meshes, armatures, materials = [], [], [], []
        collection = bpy.data.collections.new('UE_UniformScale_Temporary')
        self.scene.collection.children.link(collection)
        try:
            if context.object is not None and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            data = bpy.data.armatures.new('UE_Skin_Temporary')
            armatures.append(data)
            rig = bpy.data.objects.new('UE_Skin_Temporary', data)
            objects.append(rig)
            rig.delta_location = (0, 0, 0)
            rig.delta_rotation_euler = (0, 0, 0)
            rig.delta_rotation_quaternion = (1, 0, 0, 0)
            rig.delta_scale = (1, 1, 1)
            rig.parent = None
            rig.hide_viewport = rig.hide_render = rig.hide_select = False
            collection.objects.link(rig)
            rig.hide_set(False)
            for name in (export.ROLE_ID_PROPERTY, export.ROLE_OWNER_PROPERTY):
                if name in rig:
                    del rig[name]
            self.scale_matrix = Matrix.Scale(self.factor, 4)
            self.scale_array = np.asarray(self.scale_matrix, dtype=np.float64)
            self.inverse_scale_array = np.linalg.inv(self.scale_array)
            for obj in context.selected_objects:
                obj.select_set(False)
            context.view_layer.objects.active = rig
            rig.select_set(True)
            bpy.ops.object.mode_set(mode='EDIT')
            for index, name in enumerate(self.names):
                bone = data.edit_bones.new(name)
                matrix = Matrix(self.rest[name])
                matrix.translation *= self.factor
                source_name = self.layout['source_names'][index]
                original = self.source.data.bones.get(source_name) if source_name is not None else None
                length = original.length * self.factor if original else max(self.factor, 0.01)
                bone.head = matrix.translation
                bone.tail = bone.head + matrix.to_3x3().col[1].normalized() * length
                bone.align_roll(matrix.to_3x3().col[2])
                parent = self.skeleton['parents'][index]
                if parent >= 0:
                    bone.parent = data.edit_bones[self.names[parent]]
            bpy.ops.object.mode_set(mode='OBJECT')
            for name, source_name in zip(self.names, self.layout['source_names']):
                bone = data.bones[name]
                original = self.source.data.bones.get(source_name) if source_name is not None else None
                if original is None:
                    bone['blender_ue_export_root'] = True
                else:
                    bone.inherit_scale = original.inherit_scale
                    bone.use_inherit_rotation = original.use_inherit_rotation
                    bone.use_local_location = original.use_local_location
            data.pose_position = 'POSE'
            self.normal_rest = {b.name: np.asarray(b.matrix_local, dtype=np.float64) for b in data.bones}
            copies, material_map = [], {}
            for original in self.meshes:
                obj = original.copy()
                objects.append(obj)
                collection.objects.link(obj)
                if original.data.shape_keys:
                    # Snapshot the neutral basis without creating/removing Key IDs.
                    flags = [(m, m.show_viewport) for m in obj.modifiers]
                    for modifier, _shown in flags:
                        modifier.show_viewport = False
                    context.view_layer.update()
                    graph = context.evaluated_depsgraph_get()
                    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph),
                        preserve_all_data_layers=True, depsgraph=graph)
                    for modifier, shown in flags:
                        modifier.show_viewport = shown
                else:
                    mesh = original.data.copy()
                meshes.append(mesh)
                obj.data = mesh
                aliases = {source: name for name, source in zip(self.names, self.layout['source_names'])
                           if source is not None}
                groups = []
                for group in list(obj.vertex_groups):
                    if group.name not in aliases:
                        obj.vertex_groups.remove(group)
                    else:
                        name = aliases[group.name]
                        group.name = '__UE_group_' + str(group.index)
                        groups.append((group, name))
                for group, name in groups:
                    group.name = name
                obj.animation_data_clear()
                obj.delta_location = (0, 0, 0)
                obj.delta_rotation_euler = (0, 0, 0)
                obj.delta_rotation_quaternion = (1, 0, 0, 0)
                obj.delta_scale = (1, 1, 1)
                obj.parent = None
                obj.hide_viewport = obj.hide_render = obj.hide_select = False
                obj.hide_set(False)
                for modifier in obj.modifiers:
                    if modifier.type == 'ARMATURE':
                        modifier.object = rig
                # Material IDs are shared read-only. Repair the exported scalar
                # metadata below, keeping FBX material/slot names stable on updates.
                copies.append(obj)
            for bone in rig.pose.bones:
                bone.rotation_mode = 'QUATERNION'
            yield rig, copies
        finally:
            if context.object is not None and context.object.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in reversed(objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            for mesh in meshes:
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)
            for data in armatures:
                if data.users == 0:
                    bpy.data.armatures.remove(data)
            for material in materials:
                if material.users == 0:
                    bpy.data.materials.remove(material)
            bpy.data.collections.remove(collection)
            self.scene.frame_set(old_frame, subframe=old_sub)
            context.view_layer.update()
            for obj in context.view_layer.objects:
                if obj.select_get():
                    obj.select_set(False)
            for obj in old_selected:
                if obj.name in context.view_layer.objects:
                    obj.select_set(True)
            context.view_layer.objects.active = old_active
            if old_active is not None and old_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode=old_mode)

    def _pose_copies(self, rig, copies, graph):
        original = self.source.evaluated_get(graph)
        rig.matrix_world = original.matrix_world @ self.scale_matrix.inverted()
        desired = {}
        for name, source_name in zip(self.names, self.layout['source_names']):
            source_pose = np.asarray(live_link_pose.source_matrix(original, source_name), dtype=np.float64)
            matrix = (self.scale_array @ source_pose @ self.rest_inverse[name] @
                      self.inverse_scale_array @ self.normal_rest[name])
            desired[name] = Matrix(matrix)
        for name in self.names:
            pose_bone = rig.pose.bones[name]
            bone = pose_bone.bone
            if pose_bone.parent:
                pose_bone.matrix_basis = bone.convert_local_to_pose(
                    desired[name], bone.matrix_local, parent_matrix=desired[pose_bone.parent.name],
                    parent_matrix_local=pose_bone.parent.bone.matrix_local, invert=True)
            else:
                pose_bone.matrix_basis = bone.convert_local_to_pose(
                    desired[name], bone.matrix_local, invert=True)
        for original_mesh, copy in zip(self.meshes, copies):
            copy.matrix_world = original_mesh.evaluated_get(graph).matrix_world
        self.context.view_layer.update()

    def _validate(self, rig, copies):
        maximum, bone_maximum = 0.0, 0.0
        manager = self.context.window_manager
        manager.progress_begin(0, len(self.frames))
        try:
            for index, frame in enumerate(self.frames):
                self.scene.frame_set(math.floor(frame), subframe=frame - math.floor(frame))
                self.context.view_layer.update()
                validate_stream(self.source, self.scene, self.guard)
                graph = self.context.evaluated_depsgraph_get()
                for obj in self.meshes:
                    if obj.data.shape_keys and any(k != obj.data.shape_keys.reference_key and abs(k.value) > 1e-7
                                                   for k in obj.data.shape_keys.key_blocks):
                        raise ValueError(f'网格“{obj.name}”含动画形态键；当前只同步骨骼动作，请在副本中分离表情动画。')
                original_points = [_points(obj, graph) for obj in self.meshes]
                original = self.source.evaluated_get(graph)
                source_heads = {n: (original.matrix_world @ original.pose.bones[source].head,
                                   original.matrix_world @ original.pose.bones[source].tail)
                                for n, source in zip(self.names, self.layout['source_names']) if source is not None}
                # Also verify the unchanged live packets can carry every sampled pose.
                live_link_protocol.encode_frame('BlenderUELiveLink', 9007199254740991, frame,
                    live_link_pose.extract_unreal_local_transforms(
                        self.source, self.scene, self.layout))
                self._pose_copies(rig, copies, graph)
                graph = self.context.evaluated_depsgraph_get()
                for points, obj in zip(original_points, copies):
                    actual = _points(obj, graph)
                    if actual.shape != points.shape:
                        raise ValueError('统一缩放后网格结构发生变化，已停止同步。')
                    error = float(np.linalg.norm(points - actual, axis=1).max(initial=0)) * self.unit
                    maximum = max(maximum, error)
                for name, (head, tail) in source_heads.items():
                    bone = rig.pose.bones[name]
                    bone_maximum = max(bone_maximum,
                        ((rig.matrix_world @ bone.head) - head).length * self.unit,
                        ((rig.matrix_world @ bone.tail) - tail).length * self.unit)
                if max(maximum, bone_maximum) > POSITION_TOLERANCE_METERS:
                    raise ValueError(f'统一缩放后模型或动作偏差超出 0.1 毫米（帧 {frame:g}），已停止同步。')
                manager.progress_update(index + 1)
        finally:
            manager.progress_end()
        self.report = {'factor': self.factor, 'samples': len(self.frames),
                       'max_vertex_error_m': maximum, 'max_bone_endpoint_error_m': bone_maximum,
                       'source_preserved': True}

    def export(self, payload, request_id):
        if not self.isolated:
            return export.export_character(self.context, self.source, payload, request_id, inspected=self.inspected)
        original_frame, original_sub = self.scene.frame_current, self.scene.frame_subframe
        role = export.role_id(self.source)
        with self._copies() as (rig, copies):
            self._validate(rig, copies)
            self.scene.frame_set(original_frame, subframe=original_sub)
            self.context.view_layer.update()
            self._pose_copies(rig, copies, self.context.evaluated_depsgraph_get())
            if export.geometry_signature(self.source, self.meshes, self.context) != self.signature:
                raise ValueError('验证期间原角色发生变化，已停止同步，请重试。')
            self._pose_copies(rig, copies, self.context.evaluated_depsgraph_get())
            inspected = export.inspect_character(self.context, rig)
            result = export.export_character(self.context, rig, payload, request_id, inspected=inspected)
        # Stable ORIGINAL role and source-reference frame keep normal updates and
        # direct pose streaming working after every temporary object is removed.
        result.update(role_id=role, role_name=self.source.name, skeleton=self.skeleton,
                      geometry_signature=self.signature, meshes=[obj.name for obj in self.meshes],
                      uniform_scale_preparation=self.report)
        result['warnings'].append(
            f'已在导出副本整理蒙皮骨架及缩放（原世界比例 {self.factor:g}）；'
            f'{self.report["samples"]} 个姿态采样通过，原角色及动画保留。')
        for material, repairs in self.repairs.items():
            for _node, socket, old, value in repairs:
                field = 'metallic' if socket == 'Metallic' else 'roughness'
                for record in result['materials']:
                    if record['name'] == material.name:
                        record[field] = value
                result['warnings'].append(f'导出副本材质“{material.name}”的 {socket} 已从 {old:g} 规范化为 {value:g}。')
        return result


def prepare_character(context, armature, enabled=True):
    return CharacterPreparation(context, armature, enabled=enabled)
