"""Export one evaluated static mesh at its pivot, with world TRS sent separately."""
import hashlib
import math
from pathlib import Path

import bpy
from mathutils import Matrix

from . import api_compat, character_export, live_link_pose, static_sender


def role_id(obj):
    # Shared identity rules protect copies and cross-kind accidental reuse.
    return character_export.role_id(obj)


def transform_data(obj, scene, context=None):
    if obj is None or obj.type != 'MESH':
        raise ValueError('请选择静态网格对象。')
    context = context or bpy.context
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    matrix = evaluated.matrix_world.copy()
    if any(not math.isfinite(float(value)) for row in matrix for value in row):
        raise ValueError('静态模型变换包含无效数值。')
    axes = [matrix.to_3x3().col[index].copy() for index in range(3)]
    if (matrix.to_3x3().determinant() <= 0 or
            any(axis.length <= 1e-8 for axis in axes) or
            any(abs(axes[a].normalized().dot(axes[b].normalized())) > 1e-5
                for a, b in ((0, 1), (0, 2), (1, 2)))):
        raise ValueError('静态模型世界变换含镜像、零缩放或剪切；请先整理对象及父级变换。')
    unit = float(scene.unit_settings.scale_length)
    if not math.isfinite(unit) or unit <= 0:
        raise ValueError('场景单位比例不正确。')
    return static_sender.validate_transform(
        list(live_link_pose._to_unreal_transform(matrix, unit * 100.0)))


def _feed_material(digest, material):
    feed = character_export._feed
    feed(digest, material.name if material else '')
    if material is None:
        return
    values, image, _ = character_export._material_values(material)
    feed(digest, values)
    if image is not None:
        source = Path(bpy.path.abspath(image.filepath))
        feed(digest, [image.name, image.source, str(source), bool(image.is_dirty)])
        if image.packed_file is not None:
            feed(digest, hashlib.sha256(bytes(image.packed_file.data)).hexdigest())
        elif source.is_file():
            stat = source.stat()
            feed(digest, [stat.st_size, stat.st_mtime_ns])


def geometry_signature(obj, context):
    """Hash evaluated local geometry/materials, intentionally excluding object TRS."""
    digest = hashlib.sha256()
    feed = character_export._feed
    rounded = character_export._rounded
    feed(digest, float(context.scene.unit_settings.scale_length))
    graph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        feed(digest, [len(mesh.vertices), len(mesh.polygons)])
        for vertex in mesh.vertices:
            feed(digest, rounded(vertex.co))
        for polygon in mesh.polygons:
            feed(digest, [list(polygon.vertices), polygon.material_index, polygon.use_smooth])
        for name, coordinates in api_compat.uv_layers(mesh):
            feed(digest, name)
            for coordinate in coordinates:
                feed(digest, rounded(coordinate))
        for normal in api_compat.corner_normals(mesh):
            feed(digest, rounded(normal))
        for material in mesh.materials:
            _feed_material(digest, material)
    finally:
        evaluated.to_mesh_clear()
    return digest.hexdigest()


def inspect_static_mesh(context, obj):
    if obj is None or obj.type != 'MESH' or obj.find_armature() is not None:
        raise ValueError('请选择未绑定骨架的静态网格对象。')
    if obj.library is not None or obj.override_library is not None:
        raise ValueError('请先将模型设为本地可编辑对象。')
    selected_meshes = [item for item in context.selected_objects if item.type == 'MESH']
    if len(selected_meshes) > 1:
        raise ValueError('静态模型当前一次同步一个网格，请只选中要同步的网格对象。')
    if obj.mode == 'EDIT':
        editing_meshes = [item for item in context.objects_in_mode if item.type == 'MESH']
        if context.object != obj or len(editing_meshes) != 1:
            raise ValueError('编辑模式下请只编辑当前要同步的一个网格。')
        # Flush the live edit BMesh into Mesh data before validation/evaluation.
        # The exporter already restores the original EDIT mode and selection.
        obj.update_from_editmode()
    if any(mod.type == 'ARMATURE' and mod.object is not None for mod in obj.modifiers):
        raise ValueError('含骨架修改器的网格请使用角色同步。')
    context.view_layer.update()
    transform = transform_data(obj, context.scene, context)
    graph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        if not mesh.vertices or not mesh.polygons:
            raise ValueError('静态模型没有可导出的网格面。')
        if any(not math.isfinite(float(value)) for vertex in mesh.vertices for value in vertex.co):
            raise ValueError('静态模型顶点包含无效坐标。')
    finally:
        evaluated.to_mesh_clear()
    return transform, geometry_signature(obj, context)


def export_static_mesh(context, obj, payload_dir, request_id, inspected=None):
    transform, signature = inspected if inspected is not None else inspect_static_mesh(context, obj)
    payload_dir = Path(payload_dir)
    previous_active = context.view_layer.objects.active
    previous_selected = list(context.selected_objects)
    previous_mode = previous_active.mode if previous_active is not None else 'OBJECT'
    temporary_object = temporary_mesh = None
    try:
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        graph = context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(graph)
        temporary_mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=graph)
        temporary_object = bpy.data.objects.new('StaticMeshExport', temporary_mesh)
        context.scene.collection.objects.link(temporary_object)
        temporary_object.matrix_world = Matrix.Identity(4)
        bpy.ops.object.select_all(action='DESELECT')
        temporary_object.select_set(True)
        context.view_layer.objects.active = temporary_object
        context.view_layer.update()
        materials, warnings = character_export.export_materials(
            [temporary_object], payload_dir, request_id)
        result = api_compat.export_fbx(payload_dir / 'character.fbx', model_type='static')
        if result != {'FINISHED'}:
            raise ValueError('静态网格 FBX 导出未完成。')
    finally:
        if context.object is not None and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        if temporary_object is not None:
            bpy.data.objects.remove(temporary_object, do_unlink=True)
        if temporary_mesh is not None and temporary_mesh.users == 0:
            bpy.data.meshes.remove(temporary_mesh)
        bpy.ops.object.select_all(action='DESELECT')
        for item in previous_selected:
            item.select_set(True)
        context.view_layer.objects.active = previous_active
        context.view_layer.update()
        if previous_active is not None and previous_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=previous_mode)
    return {'model_type': 'static', 'role_id': role_id(obj), 'role_name': obj.name,
            'transform': transform, 'geometry_signature': signature, 'materials': materials,
            'meshes': [obj.name], 'warnings': warnings}
