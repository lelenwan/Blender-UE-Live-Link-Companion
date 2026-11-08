# Copyright (c) 2026 YanNick.
"""Display-only translations; protocol values and user-provided names stay intact."""
import re

import bpy

CONTEXT = 'BlenderUELiveLink'

# Chinese messages remain the internal status/error IDs used by the sync modules.
CATALOG = {
    '请选择 UE 工程': 'Select a UE Project',
    '刷新后选择正在运行的 UE 工程': 'Refresh and select a running UE project',
    '自动刷新在线工程，由你选择同步目标': 'Online projects refresh automatically; select a sync target',
    '正在查找运行中的 UE 工程…': 'Searching for running UE projects…',
    '未发现在线工程，请等待 UE 加载完成并启用本版同步插件。': 'No online projects found. Wait for UE to finish loading and enable this version of the sync plugin.',
    '请选择带 Armature 修改器的蒙皮模型或其绑定骨架。': 'Select a skinned mesh with an Armature modifier or its bound armature.',
    '所选模型没有绑定蒙皮骨架。': 'The selected model has no bound armature.',
    '请选中一个静态网格、角色网格或骨架。': 'Select a static mesh, skinned mesh, or armature.',
    '所选骨架没有绑定蒙皮网格，请用吸管选择模型。': 'The selected armature has no skinned mesh. Use the eyedropper to select the model.',
    '请选择模型，然后同步到所选工程。': 'Select a model, then sync it to the selected project.',
    '请先成功同步此模型到当前 UE 工程。': 'Sync this model to the current UE project successfully first.',
    '保存时更新已启用；只有网格、UV 或材质变化才重新导入。': 'Update on Save is enabled; only mesh, UV, or material changes trigger a reimport.',
    '静态模型目标不可用或已改为骨骼网格。': 'The static mesh target is unavailable or now has an armature.',
    'Live Link 目标骨架不可用。': 'The Live Link target armature is unavailable.',
    '尚未取得 UE 实际接收端口，请先同步模型，或填写 UE Source 显示的端口。': 'No UE receiver port is available. Sync the model first, or enter the port shown by the UE Source.',
    '所选 UE 工程会话已失效，发送已暂停；恢复在线后请重新选择。': 'The selected UE session expired. Streaming is paused; select the project again when it is online.',
    '正在等待 UE 完成上一次同步。': 'Waiting for UE to finish the previous sync.',
    '目标 UE 插件尚不支持静态模型，请安装新版 UE 插件并重启工程。': 'The target UE plugin does not support static meshes. Install the newer UE plugin and restart the project.',
    'UE 当前预览的是另一个模型，请手动同步后再启用自动更新。': 'UE is previewing another model. Sync manually before enabling automatic updates.',
    '模型未变化，已跳过重新导入；变换或动作继续实时发送。': 'The model is unchanged; reimport skipped. Transforms or animation continue streaming.',
    '此模型尚未同步到当前工程，请先点击“同步模型”。': 'This model has not been synced to the current project. Click Sync Model first.',
    '正在导出静态模型…': 'Exporting static mesh…',
    '正在导出角色…': 'Exporting character…',
    'UE 当前预览目标已变化，自动更新已停止。': 'The UE preview target changed. Automatic updates stopped.',
    '模型已发送，等待 UE 导入并配置连接…': 'Model sent. Waiting for UE to import it and configure the connection…',
    '等待 UE 超时，请检查 UE 日志。不要重复点击；先确认上一请求的结果。': 'UE timed out. Check the UE log and the previous request result before retrying.',
    'UE 同步未完成。': 'UE sync did not complete.',
    'UE 返回的模型类型与当前请求不一致。': 'The model type returned by UE does not match this request.',
    '模型同步完成，正在发送变换或动作。': 'Model sync complete. Streaming transforms or animation.',
    '（有提示，请展开详细信息）': ' (see Details for notes)',
    ' 自动更新已暂停。': ' Automatic updates paused.',
    'UE 预览目标已改变，发送已暂停，请重新同步模型。': 'The UE preview target changed. Streaming is paused; sync the model again.',
    '同步目标已变化，请重新启用保存时更新。': 'The sync target changed. Enable Update on Save again.',
    '蒙皮骨架': 'Skinned Armature',
    '可用吸管点击蒙皮模型，自动选择其 Armature 修改器绑定的骨架': 'Use the eyedropper on a skinned mesh to select the armature bound by its Armature modifier',
    'UE 地址': 'UE Address',
    'UE 端口': 'UE Port',
    '0 表示尚未取得 UE 分配的实际接收端口': '0 means the actual receiver port assigned by UE is not available yet',
    '发送 FPS': 'Stream FPS',
    'UE 工程': 'UE Project',
    '资源目录': 'Asset Directory',
    '统一缩放后同步': 'Normalize Scale Before Sync',
    '在导出副本整理固定正数等比骨架缩放并验证动作；保留原角色，不自动保存文件': 'Normalize fixed positive uniform armature scale on an export copy and validate animation; preserve the original character without saving the file',
    '保存时更新模型': 'Update Model on Save',
    '首次同步成功后启用，仅模型变化时重新导入；失败时自动暂停': 'Enable after the first successful sync; reimport only when the model changes and pause automatically on failure',
    '打开 UE 工程，刷新并选择同步目标。': 'Open a UE project, refresh, and select a sync target.',
    '详细信息': 'Details',
    '手动连接': 'Manual Connection',
    '刷新工程': 'Refresh Projects',
    '查找本机已运行并启用模型同步插件的 UE 工程': 'Find local running UE projects with the model sync plugin enabled',
    '同步模型': 'Sync Model',
    '发送活动静态网格或骨骼角色，创建专用资源并配置预览': 'Send the active static mesh or skinned character, create dedicated assets, and configure the preview',
    '更新模型': 'Update Model',
    '更新当前模型资源；保留 UE 中的材质分配': 'Update the current model assets while preserving material assignments in UE',
    '启动 Live Link': 'Start Live Link',
    '发送静态模型变换或骨骼姿态，模型资源不重新导入': 'Stream static mesh transforms or skeletal poses without reimporting model assets',
    '静态模型需要选择新版 UE 工程并先点击“同步模型”。': 'For static meshes, select a project using the newer UE plugin and click Sync Model first.',
    '请先将此静态模型同步到当前 UE 工程。': 'Sync this static mesh to the current UE project first.',
    '请先点击“同步模型”建立本次连接。': 'Click Sync Model to establish this connection first.',
    '请先将此角色同步到所选 UE 工程。': 'Sync this character to the selected UE project first.',
    '模型变换或动作发送已启动。': 'Streaming model transforms or animation.',
    '停止 Live Link': 'Stop Live Link',
    '停止发送模型变换或骨骼姿态': 'Stop streaming model transforms or skeletal poses',
    '静态模型：': 'Static Model: ',
    '整理导出副本，保留原角色与动画。': 'Prepare an export copy; preserve the original character and animation.',
    '同步：正在发送': 'Sync: Streaming',
    '同步：已停止': 'Sync: Stopped',
    'UE 工程未响应，请刷新。': 'The UE project is not responding. Refresh the project list.',
    '同时预览一个模型；静态网格一次发送一个活动对象。': 'Preview one model at a time; stream one active object for static meshes.',
    '静态模型支持正数缩放；剪切和镜像变换会停止发送。': 'Static meshes support positive scale; shear and mirrored transforms stop streaming.',
    '支持基础材质与贴图；保留 UE 中替换的材质。': 'Basic materials and textures are supported; material overrides in UE are preserved.',
    '统一缩放支持固定正数等比缩放；动作验证失败会停止同步。': 'Scale normalization supports fixed positive uniform scale; failed animation validation stops sync.',
    '旧版 UE 仅支持骨骼姿态，需手动 Source 和动画蓝图。': 'Legacy UE supports skeletal poses only; configure the Source and Animation Blueprint manually.',
    '模型绑定了多套骨架，请先保留单一蒙皮骨架。': 'The model uses multiple armatures. Keep a single skinning armature first.',
    '角色需要且只能有一根根骨骼；请先整理骨架层级。': 'A character must have exactly one root bone. Fix the bone hierarchy first.',
    '所选骨架没有骨骼。': 'The selected armature has no bones.',
    '请选中角色网格或指定目标骨架。': 'Select a character mesh or specify the target armature.',
    '请退出骨架编辑模式后再同步。': 'Exit Armature Edit Mode before syncing.',
    '请先将角色设为本地可编辑对象。': 'Make the character a local editable object first.',
    '骨架对象缩放须为 1；请先应用缩放，避免 UE 模型与动作比例不同。': 'Armature object scale must be 1. Apply scale first to keep the UE model and animation at the same scale.',
    '骨架的父级引入了缩放、镜像或剪切；请先应用父级变换，保持骨架世界缩放为 1。': 'The armature parent introduces scale, mirroring, or shear. Apply parent transforms and keep the armature world scale at 1.',
    '所选骨架没有绑定网格；请检查 Armature 修改器。': 'The selected armature has no bound mesh. Check the Armature modifier.',
    'FBX 导出未完成。': 'FBX export did not complete.',
    '骨架世界变换含无效数值。': 'The armature world transform contains invalid values.',
    '骨架世界变换含镜像或剪切，不能自动统一。': 'The armature world transform contains mirroring or shear and cannot be normalized automatically.',
    '当前动作范围过长，统一缩放需要分段验证；请先整理为较短的烘焙动作。': 'The animation range is too long for scale validation. Use shorter baked actions first.',
    '统一缩放的动作采样数超出上限，请先整理为较短的烘焙动作。': 'Scale validation exceeds the pose sample limit. Use shorter baked actions first.',
    '统一缩放的角色或骨架已改变，请重新同步模型。': 'The normalized character or armature changed. Sync the model again.',
    '骨架父级已改变，请重新同步模型。': 'The armature parent changed. Sync the model again.',
    '场景单位已改变，请重新同步模型。': 'Scene units changed. Sync the model again.',
    '骨架对象缩放已改变，请重新统一缩放并同步模型。': 'The armature object scale changed. Normalize scale and sync the model again.',
    '骨架结构已改变，请重新同步模型。': 'The armature structure changed. Sync the model again.',
    '骨架参考姿态已改变，请重新同步模型。': 'The armature reference pose changed. Sync the model again.',
    '请选中角色网格或骨架。': 'Select a character mesh or armature.',
    '请退出骨架编辑模式后再统一缩放。': 'Exit Armature Edit Mode before normalizing scale.',
    '统一缩放需要本地可编辑骨架。': 'Scale normalization requires a local editable armature.',
    '骨架已禁用视口求值，请先启用骨架再统一缩放。': 'Viewport evaluation is disabled for the armature. Enable it before normalizing scale.',
    '请将骨架切到“姿态位置”后再统一缩放。': 'Switch the armature to Pose Position before normalizing scale.',
    '本版暂不自动整理带父级的非单位骨架，请先在独立副本中整理父级。': 'Automatic normalization of a parented armature with non-unit scale is not supported. Prepare its parent transforms on a separate copy first.',
    '骨架对象的缩放随动画变化，本版只支持固定等比缩放。': 'The armature object scale is animated. Only fixed uniform scale is supported.',
    '所选骨架没有绑定网格，请检查 Armature 修改器。': 'The selected armature has no bound mesh. Check the Armature modifier.',
    '场景单位比例无效。': 'The scene unit scale is invalid.',
    '骨骼名称在 UE 中存在大小写冲突，请先整理名称。': 'Bone names have a case-insensitive conflict in UE. Rename the conflicting bones first.',
    '统一缩放后网格结构发生变化，已停止同步。': 'Mesh topology changed after scale normalization. Sync stopped.',
    '验证期间原角色发生变化，已停止同步，请重试。': 'The original character changed during validation. Sync stopped; try again.',
    '同步记录过大。': 'The sync record is too large.',
    '同步目录不能使用符号链接或目录联接。': 'The sync directory cannot use symbolic links or directory junctions.',
    '同步文件路径不正确。': 'The sync file path is invalid.',
    '同步文件超出目标目录。': 'The sync file is outside the target directory.',
    'UE 同步插件协议不兼容。': 'The UE sync plugin protocol is incompatible.',
    'UE 会话标识不正确。': 'The UE session ID is invalid.',
    'UE 工程已关闭或未响应，请刷新工程列表。': 'The UE project is closed or not responding. Refresh the project list.',
    'UE 工程路径不可用。': 'The UE project path is unavailable.',
    'UE 同步目录与工程不匹配。': 'The UE sync directory does not match the project.',
    'UE 接收端口不正确。': 'The UE receiver port is invalid.',
    'UE 静态模型接收端口不正确。': 'The UE static mesh receiver port is invalid.',
    '请先选择正在运行的 UE 工程。': 'Select a running UE project first.',
    '找不到所选 UE 工程，请刷新列表。': 'The selected UE project was not found. Refresh the list.',
    '同步请求标识不正确。': 'The sync request ID is invalid.',
    '角色或请求标识不正确。': 'The character or request ID is invalid.',
    '同步操作不正确。': 'The sync operation is invalid.',
    '同步模型类型不正确。': 'The sync model type is invalid.',
    '目标 UE 插件尚不支持静态模型，请升级 UE 插件。': 'The target UE plugin does not support static meshes. Upgrade the UE plugin.',
    '静态模型变换不正确。': 'The static mesh transform is invalid.',
    '静态模型旋转四元数未归一化。': 'The static mesh rotation quaternion is not normalized.',
    '静态模型位置或缩放超出支持范围。': 'The static mesh position or scale is outside the supported range.',
    '资源目录须位于 /Game/BlenderLiveLink 下，且只包含英文字母、数字和下划线。': 'The asset directory must be under /Game/BlenderLiveLink and contain only English letters, numbers, and underscores.',
    '模型 FBX 未成功导出。': 'The model FBX was not exported successfully.',
    '同步请求已提交。': 'The sync request has already been submitted.',
    'UE 返回的同步结果与当前角色不匹配。': 'The sync result returned by UE does not match the current character.',
    'UE 返回的模型类型不正确。': 'The model type returned by UE is invalid.',
    'UE 未返回可用的模型接收端口。': 'UE did not return an available model receiver port.',
    '所选骨架没有实际参与蒙皮的变形骨骼。': 'The selected armature has no deform bones contributing to skinning.',
    '静态模型变换必须是 10 个有限数值。': 'A static mesh transform must contain 10 finite values.',
    '静态模型位置超出支持范围。': 'The static mesh position is outside the supported range.',
    '静态模型仅支持正数缩放，暂不支持镜像或零缩放。': 'Static meshes require positive scale; mirrored or zero scale is not supported.',
    '静态模型同步仅支持本机回环地址。': 'Static mesh sync supports only the local loopback address.',
    '静态模型接收端口或会话标识不正确。': 'The static mesh receiver port or session ID is invalid.',
    '静态模型变换发送尚未启动。': 'Static mesh transform streaming has not started.',
    '发送序号已达上限，请重新加载插件。': 'The stream sequence limit was reached. Reload the add-on.',
    '静态模型变换数据包过大。': 'The static mesh transform packet is too large.',
    '请选择静态网格对象。': 'Select a static mesh object.',
    '静态模型变换包含无效数值。': 'The static mesh transform contains invalid values.',
    '静态模型世界变换含镜像、零缩放或剪切；请先整理对象及父级变换。': 'The static mesh world transform contains mirroring, zero scale, or shear. Fix object and parent transforms first.',
    '场景单位比例不正确。': 'The scene unit scale is invalid.',
    '请选择未绑定骨架的静态网格对象。': 'Select a static mesh object without an armature.',
    '请先将模型设为本地可编辑对象。': 'Make the model a local editable object first.',
    '静态模型当前一次同步一个网格，请只选中要同步的网格对象。': 'Static sync supports one mesh at a time. Select only the mesh object to sync.',
    '编辑模式下请只编辑当前要同步的一个网格。': 'In Edit Mode, edit only the single mesh you want to sync.',
    '含骨架修改器的网格请使用角色同步。': 'Use character sync for a mesh with an Armature modifier.',
    '静态模型没有可导出的网格面。': 'The static mesh has no faces to export.',
    '静态模型顶点包含无效坐标。': 'The static mesh vertices contain invalid coordinates.',
    '静态网格 FBX 导出未完成。': 'Static mesh FBX export did not complete.',
    '打包内容不是普通 PNG/JPG 编码，暂未传输': 'Packed data is not standard PNG/JPG; it was not sent',
    '打包贴图为空或超过 256 MiB': 'The packed texture is empty or exceeds 256 MiB',
    '当前只传输 PNG/JPG 文件': 'Only PNG/JPG files are transferred',
    '文件不存在': 'The file does not exist',
    '贴图为空或超过 256 MiB': 'The texture is empty or exceeds 256 MiB',
    '骨架世界缩放含零值、负值或无效数值，不能自动统一。': 'The armature world scale contains zero, negative, or invalid values and cannot be normalized automatically.',
    '骨架世界缩放不是等比缩放；本版只自动处理固定正数等比缩放。': 'The armature world scale is not uniform. Only fixed positive uniform scale can be normalized automatically.',
    '骨架对象缩放含零值、负值或无效数值，不能自动统一。': 'The armature object scale contains zero, negative, or invalid values and cannot be normalized automatically.',
    '骨架对象缩放不是等比缩放；本版只自动处理固定正数等比缩放。': 'The armature object scale is not uniform. Only fixed positive uniform scale can be normalized automatically.',
    '骨架增量缩放含零值、负值或无效数值，不能自动统一。': 'The armature delta scale contains zero, negative, or invalid values and cannot be normalized automatically.',
    '骨架增量缩放不是等比缩放；本版只自动处理固定正数等比缩放。': 'The armature delta scale is not uniform. Only fixed positive uniform scale can be normalized automatically.',
    '当前不支持UDIM贴图，请先转换为普通 PNG/JPG 文件': 'UDIM textures are not supported. Convert them to standard PNG/JPG files first.',
    '当前不支持视频贴图，请先转换为普通 PNG/JPG 文件': 'Movie textures are not supported. Convert them to standard PNG/JPG files first.',
    '当前不支持生成图像贴图，请先转换为普通 PNG/JPG 文件': 'Generated textures are not supported. Convert them to standard PNG/JPG files first.',
    '当前不支持图像序列贴图，请先转换为普通 PNG/JPG 文件': 'Image sequence textures are not supported. Convert them to standard PNG/JPG files first.',
    '静态模型已更新，正在同步物体变换。': 'Static mesh updated. Streaming object transforms.',
    '静态模型已导入，正在同步物体变换。': 'Static mesh imported. Streaming object transforms.',
    '角色已更新，正在等待 Blender 姿态。': 'Character updated. Waiting for Blender poses.',
    '角色已导入并配置 Live Link。': 'Character imported and Live Link configured.',
    '此同步请求正在处理。': 'This sync request is being processed.',
    'UE 编辑器尚未准备好。': 'The UE Editor is not ready yet.',
    '两端同步协议版本不一致，请更新插件。': 'The sync protocol versions do not match. Update the plugins.',
    '同步请求已过期，请在 Blender 中重新同步。': 'The sync request expired. Sync again from Blender.',
    '角色骨架需要且只能有一个根骨骼。': 'The character skeleton must have exactly one root bone.',
    '缺少有效的骨架参考变换，请更新 Blender 插件。': 'Valid skeleton reference transforms are missing. Update the Blender add-on.',
    '骨骼名称在 UE 中存在大小写重复。': 'Bone names have a case-insensitive conflict in UE.',
    '模型类型与已有同步记录不同，停止覆盖。请将其作为新模型同步。': 'The model type differs from the existing sync record. Overwrite stopped; sync it as a new model.',
    '骨架已改变，普通更新已停止。请复制完整角色（骨架和绑定网格）后，将副本作为新角色同步；原角色保留。': 'The skeleton changed. Update stopped; duplicate the entire character (armature and bound meshes) and sync the copy as a new character. The original is preserved.',
    '目标角色资源存在尚未保存的 UE 修改。请先保存或撤销这些修改，再更新模型。': 'The target character assets have unsaved UE changes. Save or discard those changes before updating the model.',
    '目标网格体已有额外 LOD，请先另存角色副本后同步。': 'The target mesh has additional LODs. Save a separate character copy before syncing.',
    '目标网格体含 Morph Target 或布料资源，请先另存副本后同步。': 'The target mesh has Morph Targets or cloth assets. Save a separate copy before syncing.',
    '材质槽名称或顺序已改变，且 UE 中存在自定义材质。请先恢复原材质槽，或作为新角色同步。': 'Material slot names or order changed and UE has custom materials. Restore the original slots or sync as a new character.',
    '无法创建基础材质。': 'Could not create the basic material.',
    '角色没有可转换的基础材质，保留 UE 默认材质。': 'The character has no convertible basic materials; UE default materials are preserved.',
    '当前静态模型更新只支持单一 LOD，请将含额外 LOD 的网格另存副本。': 'Static mesh updates support a single LOD. Save a separate copy of a mesh with additional LODs.',
    'UE 更新后的静态模型尺寸与新文件不一致，已停止更新。': 'The updated static mesh dimensions in UE differ from the new file. Update stopped.',
    '此静态模型尚未同步到当前工程，请先点击“同步模型”。': 'This static mesh has not been synced to the current project. Click Sync Model first.',
    '目标模型目录已存在但没有对应同步记录，停止覆盖。': 'The target model directory exists without a matching sync record. Overwrite stopped.',
    '原静态模型资源已被移动、替换或删除，请恢复原资源或作为新模型同步。': 'The original static mesh asset was moved, replaced, or deleted. Restore it or sync as a new model.',
    '本次更新的临时资源目录已存在，请重新发起同步。': 'The temporary asset directory for this update already exists. Start a new sync.',
    'UE 静态模型接收端口未能启动。': 'The UE static mesh receiver port could not start.',
    '此角色尚未同步到当前工程，请先点击“同步角色”。': 'This character has not been synced to the current project. Click Sync Model first.',
    '目标角色目录已存在但没有对应同步记录，停止覆盖。': 'The target character directory exists without a matching sync record. Overwrite stopped.',
    '原角色资源已被移动或删除，请恢复原目录，或复制完整角色后同步副本。': 'The original character assets were moved or deleted. Restore their directory or duplicate the entire character and sync the copy.',
    '原角色的骨架关联已改变，停止覆盖。请恢复原骨架关联后重试。': 'The original character skeleton association changed. Overwrite stopped; restore the original association and retry.',
    '模型更新改变了原骨架对象，已停止更新。': 'The model update changed the original skeleton asset. Update stopped.',
    'UE 更新后的模型尺寸与新文件不一致，已停止更新。': 'The updated model dimensions in UE differ from the new file. Update stopped.',
    '自动配置 Live Link 动画蓝图失败，请查看 UE 日志。': 'Automatic Live Link Animation Blueprint setup failed. Check the UE log.',
    'UE 姿态接收端口未能启动。': 'The UE pose receiver port could not start.',
}

# Full message templates only: captured names/paths are never searched or replaced.
TEMPLATES = (
    ('找到 {count} 个在线 UE 工程，列表自动刷新。', 'Found {count} online UE projects; the list refreshes automatically.'),
    ('找到 {online_count} 个在线 UE 工程，列表自动刷新。 {count} 条失效记录已忽略。', 'Found {online_count} online UE projects; the list refreshes automatically. {count} stale records ignored.'),
    ('未发现在线工程，请等待 UE 加载完成并启用本版同步插件。 {count} 条失效记录已忽略。', 'No online projects found. Wait for UE to finish loading and enable this version of the sync plugin. {count} stale records ignored.'),
    ('工程发现失败：{error}', 'Project discovery failed: {error}'),
    ('自动更新已暂停：{error}', 'Automatic updates paused: {error}'),
    ('UE 资源：{value}', 'UE Asset: {value}'),
    ('备份目录：{value}', 'Backup Directory: {value}'),
    ('UE 接收地址：{value}', 'UE Receiver: {value}'),
    ('UE 已接收 {count} 帧', 'UE has received {count} frames'),
    ('材质“{name}”不是直接连接的 Principled BSDF，仅传基础颜色。', 'Material “{name}” is not connected directly to Principled BSDF; only its base color is sent.'),
    ('材质“{name}”使用自定义贴图坐标，UE 基础材质使用第一套 UV。', 'Material “{name}” uses custom texture coordinates; the basic UE material uses the first UV map.'),
    ('材质“{name}”的颜色节点需要烘焙，暂传基础颜色。', 'The color nodes of material “{name}” need baking; only the base color is sent.'),
    ('材质“{name}”的透明度节点尚未转换。', 'The alpha nodes of material “{name}” have not been converted.'),
    ('材质“{name}”的金属度或粗糙度贴图尚未转换。', 'Metallic or roughness textures of material “{name}” have not been converted.'),
    ('贴图“{name}”有未保存或未重新打包的像素修改，本次使用已保存或已打包的数据。', 'Texture “{name}” has unsaved or unrepacked pixel edits; this sync uses its saved or packed data.'),
    ('请退出网格“{name}”的编辑模式后再同步。', 'Exit Edit Mode for mesh “{name}” before syncing.'),
    ('网格“{name}”被隐藏或禁止选择，请先显示后再同步。', 'Mesh “{name}” is hidden or cannot be selected. Make it visible and selectable before syncing.'),
    ('网格“{name}”含形态键；当前角色同步暂不支持形态键，请使用独立副本验证。', 'Mesh “{name}” has shape keys; character sync does not support shape keys. Validate using a separate copy.'),
    ('此骨架无法通过当前 Live Link 协议发送（单包上限 60 KiB），请精简骨骼后重试：{error}', 'This armature cannot be sent with the current Live Link protocol (60 KiB packet limit). Reduce the bone count and retry: {error}'),
    ('请先退出编辑模式并显示可选择的网格“{name}”。', 'Exit Edit Mode and make mesh “{name}” visible and selectable first.'),
    ('网格“{name}”为空，不能统一缩放。', 'Mesh “{name}” is empty and cannot be scale-normalized.'),
    ('网格“{name}”的形态键不是零值；当前只同步骨骼动作，请先归零表情后同步。', 'Mesh “{name}” has nonzero shape keys. Only skeletal animation is synced; reset expressions to zero first.'),
    ('网格“{name}”含对象动画或约束，请先在副本中烘焙。', 'Mesh “{name}” has object animation or constraints. Bake them on a copy first.'),
    ('网格“{name}”需要已启用的普通顶点组蒙皮；本版不自动转换包络或双四元数蒙皮。', 'Mesh “{name}” requires enabled standard vertex-group skinning. Envelopes and dual-quaternion skinning are not converted automatically.'),
    ('网格“{name}”由多套骨架驱动，不能自动统一缩放。', 'Mesh “{name}” is driven by multiple armatures and cannot be scale-normalized automatically.'),
    ('网格“{name}”含动画形态键；当前只同步骨骼动作，请在副本中分离表情动画。', 'Mesh “{name}” has animated shape keys. Only skeletal animation is synced; separate expression animation on a copy.'),
    ('统一缩放后模型或动作偏差超出 0.1 毫米（帧 {frame}），已停止同步。', 'Model or animation deviation exceeds 0.1 mm after scale normalization (frame {frame}). Sync stopped.'),
    ('已在导出副本整理蒙皮骨架及缩放（原世界比例 {factor}）；{samples} 个姿态采样通过，原角色及动画保留。', 'Normalized the skinned armature and scale on an export copy (original world scale {factor}); {samples} pose samples passed. The original character and animation are preserved.'),
    ('导出副本材质“{name}”的 {socket} 已从 {old} 规范化为 {value}。', 'Normalized {socket} of export-copy material “{name}” from {old} to {value}.'),
    ('需要导入一个完整骨骼网格体，实际得到 {count} 个。请确保网格绑定同一骨架。', 'Expected one complete skeletal mesh, but imported {count}. Ensure all meshes are bound to the same armature.'),
    ('需要导入一个静态网格体，实际得到 {count} 个。', 'Expected one static mesh, but imported {count}.'),
    ('无法保存静态模型资源：{value}', 'Could not save static mesh asset: {value}'),
    ('无法保存角色资源：{value}', 'Could not save character asset: {value}'),
    ('材质 {name} 的贴图导入失败，使用基础颜色。', 'Texture import failed for material {name}; using its base color.'),
    ('未找到材质槽：{name}', 'Material slot not found: {name}'),
    ('材质 {name} 含透明度；基础同步材质目前按不透明处理。', 'Material {name} has alpha; basic synced materials are currently opaque.'),
)

_PATTERNS = []
for _chinese, _english in TEMPLATES:
    _pattern = re.escape(_chinese)
    for _field in re.findall(r'\{(\w+)\}', _chinese):
        _value = r'\d+' if _field in ('count', 'online_count', 'samples') else '.*?'
        # This notice is emitted only for finite Metallic/Roughness repairs (:g).
        if '{socket}' in _chinese:
            if _field == 'socket':
                _value = r'Metallic|Roughness'
            elif _field in ('old', 'value'):
                _value = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?'
        _pattern = _pattern.replace(re.escape('{' + _field + '}'), '(?P<' + _field + '>' + _value + ')')
    _PATTERNS.append((re.compile(_pattern, re.DOTALL), _english))


def _chinese_interface():
    view = bpy.context.preferences.view
    language = view.language
    if language == 'DEFAULT':
        language = bpy.app.translations.locale
    return view.use_translate_interface and language in ('zh_HANS', 'zh_CN')


def iface(chinese):
    return chinese if _chinese_interface() else CATALOG.get(chinese, chinese)


def message(text):
    """Translate known display messages without altering their stored values."""
    if _chinese_interface() or not text:
        return text
    if text in CATALOG:
        return CATALOG[text]
    for pattern, english in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            values = match.groupdict()
            if 'error' in values:
                values['error'] = message(values['error'])
            return english.format(**values)
    # Full fields above own their captures, including suffix-like path/name text.
    for suffix in ('（有提示，请展开详细信息）', ' 自动更新已暂停。'):
        if text.endswith(suffix):
            body = text[:-len(suffix)]
            translated = message(body)
            if translated != body:
                return translated + CATALOG[suffix]
    return text


def register():
    translations = {(CONTEXT, english): chinese for chinese, english in CATALOG.items()}
    unregister()
    bpy.app.translations.register(__name__, {'zh_HANS': translations, 'zh_CN': translations})


def unregister():
    bpy.app.translations.unregister(__name__)
