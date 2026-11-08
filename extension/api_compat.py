"""Blender API boundary shared by model exporters.

Blender 5.0-5.2 use the same implementation. Future API adapters can change
mesh attribute access and FBX operator arguments here without changing model
identity, exchange files, skeleton mathematics, or the Live Link wire format.
An available capability is not a claim that an older Blender was verified.
"""
import bpy


def uv_layers(mesh):
    """Yield layer names and ordered UV coordinates while the mesh is alive."""
    for layer in mesh.uv_layers:
        yield layer.name, (loop.uv for loop in layer.data)


def corner_normals(mesh):
    """Yield the split corner normals used by the static geometry signature."""
    for normal in mesh.corner_normals:
        yield normal.vector


def _fbx_options(filepath, model_type):
    options = dict(
        filepath=str(filepath), use_selection=True, bake_anim=False,
        axis_forward='-Y', axis_up='Z', apply_unit_scale=True,
        apply_scale_options='FBX_SCALE_UNITS', use_space_transform=True,
        bake_space_transform=False, mesh_smooth_type='FACE',
        path_mode='STRIP', embed_textures=False,
    )
    if model_type == 'static':
        options.update(object_types={'MESH'}, use_mesh_modifiers=False)
    elif model_type == 'skeletal':
        options.update(
            object_types={'ARMATURE', 'MESH'}, add_leaf_bones=False,
            use_armature_deform_only=False, use_mesh_modifiers=True,
            primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
        )
    else:
        raise ValueError('Unknown FBX model type: ' + str(model_type))
    return options


def export_fbx(filepath, *, model_type):
    """Call Blender's exporter using the existing static/skeletal settings."""
    return bpy.ops.export_scene.fbx(**_fbx_options(filepath, model_type))


def capabilities():
    """Describe the current API for diagnostics; do not infer tested support."""
    required = set(_fbx_options('', 'static')) | set(_fbx_options('', 'skeletal'))
    try:
        available = set(bpy.ops.export_scene.fbx.get_rna_type().properties.keys())
        missing = sorted(required - available)
    except (AttributeError, RuntimeError) as error:
        missing = sorted(required)
        exporter_error = str(error)
    else:
        exporter_error = ''
    return {
        'blender_version': list(bpy.app.version),
        'blender_version_string': bpy.app.version_string,
        'fbx_required_parameters_present': not missing,
        'missing_fbx_parameters': missing,
        'fbx_operator_error': exporter_error,
        'mesh_uv_layers': 'uv_layers' in bpy.types.Mesh.bl_rna.properties,
        'mesh_corner_normals': 'corner_normals' in bpy.types.Mesh.bl_rna.properties,
    }
