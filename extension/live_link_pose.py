import bpy
import hashlib
import re
from mathutils import Matrix


BLENDER_TO_UNREAL_BASIS = Matrix(
    (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, -1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
)


def _require_armature(armature):
    if armature is None or armature.type != "ARMATURE":
        raise ValueError("armature must be a Blender ARMATURE object")


def _parent_first_bones(armature):
    bones = list(armature.data.bones)
    original_order = {bone.name: index for index, bone in enumerate(bones)}
    roots = sorted(
        (bone for bone in bones if bone.parent is None),
        key=lambda bone: original_order[bone.name],
    )
    ordered = []

    def visit(bone):
        ordered.append(bone)
        for child in sorted(
            bone.children,
            key=lambda item: original_order[item.name],
        ):
            visit(child)

    for root in roots:
        visit(root)
    if len(ordered) != len(bones):
        raise ValueError("armature hierarchy could not be traversed")
    return ordered


EXPORT_ROOT_PREFIX = '__BlenderUERoot'


def _skin_bones(armature):
    deform = {b.name for b in armature.data.bones if b.use_deform}
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and
              any(m.type == 'ARMATURE' and m.object == armature for m in obj.modifiers)]
    if not meshes:
        return deform
    weighted = set()
    for obj in meshes:
        groups = {g.index: g.name for g in obj.vertex_groups if g.name in deform}
        for vertex in obj.data.vertices:
            weighted.update(groups[g.group] for g in vertex.groups
                            if g.weight > 0.000001 and g.group in groups)
    # The temporary FK rig has one structural root without vertex weights.
    weighted.update(b.name for b in armature.data.bones if b.get('blender_ue_export_root'))
    return weighted


def build_layout(armature):
    _require_armature(armature)
    selected = _skin_bones(armature)
    ordered_bones = [b for b in _parent_first_bones(armature) if b.name in selected]
    if not ordered_bones:
        raise ValueError('所选骨架没有实际参与蒙皮的变形骨骼。')
    bone_indices = {bone.name: index for index, bone in enumerate(ordered_bones)}
    bone_names = [bone.name for bone in ordered_bones]
    source_names = list(bone_names)
    bone_parents = []
    for bone in ordered_bones:
        parent = bone.parent
        while parent is not None and parent.name not in selected:
            parent = parent.parent
        bone_parents.append(-1 if parent is None else bone_indices[parent.name])
    if bone_parents.count(-1) > 1:
        used = {b.name.casefold() for b in armature.data.bones}
        root, suffix = EXPORT_ROOT_PREFIX, 0
        while root.casefold() in used:
            suffix += 1
            root = EXPORT_ROOT_PREFIX + str(suffix)
        bone_names.insert(0, root)
        source_names.insert(0, None)
        bone_parents = [-1] + [parent + 1 if parent >= 0 else 0 for parent in bone_parents]
    # UE sanitizes FBX names (e.g. shoulder.l vs shoulder_l). Use stable aliases.
    safe = [re.sub(r'[^A-Za-z0-9_]', '_', name)[:52] or 'Bone' for name in bone_names]
    reserved = {name.casefold() for name, base in zip(bone_names, safe) if name == base}
    used, aliases = set(), []
    for name, base in zip(bone_names, safe):
        alias = base if name == base else base + '_' + hashlib.sha256(name.encode()).hexdigest()[:8]
        suffix = 0
        while alias.casefold() in used or (alias.casefold() in reserved and alias != name):
            suffix += 1
            alias = base + '_' + hashlib.sha256((name + str(suffix)).encode()).hexdigest()[:8]
        used.add(alias.casefold())
        aliases.append(alias)
    return {'names': aliases, 'parents': bone_parents, 'source_names': source_names}


def build_skeleton(armature):
    layout = build_layout(armature)
    return layout['names'], layout['parents']


def source_matrix(armature, name, rest=False):
    if name is None:
        return Matrix.Identity(4)
    bone = armature.data.bones.get(name) if rest else armature.pose.bones.get(name)
    if bone is not None:
        return bone.matrix_local if rest else bone.matrix
    raise ValueError(f'pose bone not found: {name}')


def _to_unreal_transform(local_matrix, centimeters_per_blender_unit):
    converted = BLENDER_TO_UNREAL_BASIS @ local_matrix @ BLENDER_TO_UNREAL_BASIS
    location, rotation, scale = converted.decompose()
    rotation.normalize()
    location *= centimeters_per_blender_unit
    return (
        float(location.x),
        float(location.y),
        float(location.z),
        float(rotation.x),
        float(rotation.y),
        float(rotation.z),
        float(rotation.w),
        float(scale.x),
        float(scale.y),
        float(scale.z),
    )


def extract_unreal_local_transforms(armature, scene, skeleton=None):
    _require_armature(armature)
    if scene is None:
        raise ValueError("scene is required")

    layout = skeleton if skeleton is not None else build_layout(armature)
    bone_names, bone_parents, sources = layout['names'], layout['parents'], layout['source_names']
    dependency_graph = bpy.context.evaluated_depsgraph_get()
    evaluated_armature = armature.evaluated_get(dependency_graph)
    centimeters_per_blender_unit = float(scene.unit_settings.scale_length) * 100.0
    transforms = []

    for source_name, parent in zip(sources, bone_parents):
        matrix = source_matrix(evaluated_armature, source_name)
        if parent < 0:
            local_matrix = evaluated_armature.matrix_world @ matrix
        else:
            local_matrix = source_matrix(evaluated_armature, sources[parent]).inverted_safe() @ matrix
        transforms.append(
            _to_unreal_transform(local_matrix, centimeters_per_blender_unit)
        )

    return transforms
