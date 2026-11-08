BLENDER UE LIVE LINK
Publisher: YanNick
Support: 16759624@qq.com

Purpose
Transfer a skinned character or static mesh from Blender to Unreal Engine and
preview evaluated motion through Live Link on the same Windows computer.
Blender keeps the IK controllers, constraints and animation. Unreal receives
the weighted deform-bone pose and a structural root where one is required.

Requirements
- Windows 64-bit, a supported Blender installation, and a matching UE version.
- UE Live Link, Python Editor Script Plugin and Editor Scripting Utilities.
  The latter two built-in UE plugins are beta dependencies. Enable them and
  restart the editor when requested. They are not distributed with this tool.
- Blender is installed separately from https://www.blender.org/download/.
- This product does not include Blender, Unreal Engine, a character model,
  character animations, or an animation-generation service.

Installing the Fab edition
1. Add the plugin to the supported engine version through Fab/Launcher.
2. Enable Blender UE Live Link and its required plugins in your UE project.
3. Locate the Blender extension ZIP in the plugin's
   Source/ThirdParty/BlenderExtension directory. In Blender, open Preferences,
   use Install from Disk in the extensions/add-ons menu, select that ZIP and
   enable Blender UE Live Link.
4. Keep only one active copy of the UE plugin. Back up and remove an obsolete
   project-level copy before switching to an engine-installed Fab copy.

Installing the Windows offline edition
Extract the complete offline ZIP to a writable folder. Save and close Blender
and UE, then run Install-LiveLink.cmd and select the applications and target
project or engine. This installer is a separate distribution, not a Fab Code
Plugin upload. Installation backs up replaced files; success remains visible
until you return or close the installer.

Starting a character session
1. Open the UE project and wait for its editor to finish loading.
2. Open the character in Blender. In the 3D View, press N and select UE Live Link.
3. Choose the running UE project. Use the Skinned Armature eyedropper on a mesh
   to select the armature actually bound through its Armature modifier.
4. Leave Normalize Scale enabled and select Sync Model. Wait for import and
   the actual receiving port. Automatic setup does not need another Add Source.
5. Move an IK controller, insert keyframes or play the timeline. The preview
   receives the evaluated deform-bone motion; no manual bake is required.
6. Use Stop Live Link when finished. Re-select and synchronize after restarting UE.

Static meshes and model changes
Select an unbound static mesh and synchronize it once. Subsequent transform
changes stream without reimporting geometry. Use Update Model after changing
mesh data, weights, UVs or supported material inputs. Pose playback alone does
not trigger model reimport. Save-time model updates are optional after a
successful first synchronization.

Language
The Blender panel follows Blender's interface translation preference. English
and Simplified Chinese are provided. Object names, bone names, filesystem
paths and raw third-party diagnostics retain their original text.

Important limits
- Communication is local to one computer. Port 0 means no actual port has been
  obtained; it is not a destination to send to.
- One preview role is active at a time. This streams poses; it does not
  automatically create or record a UE Animation Sequence asset.
- Ordinary vertex-group skinning, fixed positive uniform object scaling and
  supported basic materials are required. Mirroring, shear, changing object
  scale, envelope/DQS skinning and multiple-armature skinning are not converted.
- Neutral shape keys may export their basis. Morph/facial animation, cloth,
  complex materials and continuous geometry streaming are not supported.
- Old exports that included controller bones may have a different hierarchy.
  Keep the old project and import into a separate test project before migration.

Troubleshooting
No project: confirm the UE editor plugin and required dependencies are enabled;
wait for editor startup, then refresh the project list.
Waiting source: check the actual nonzero port. Remove an obsolete manually
created source only after confirming it is not the active receiving source.
Preview pauses in the background: enable real-time viewport updates and review
UE's Use Less CPU when in Background preference.
Export rejected: read the error, show selectable bound meshes and check the
supported skinning, scale and shape-key limits. Do not delete source constraints.

Licenses and support
The Blender extension has its own GPL-3.0-or-later license and upstream notice.
See its COPYING.txt and NOTICE.txt. These are separate from the license for
the UE integration. Include your Blender/UE versions and a description of the
problem when contacting 16759624@qq.com. Do not send private project files
unless you choose to share them.
