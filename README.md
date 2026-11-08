# Blender UE Live Link - Blender companion

Free Blender companion extension maintained by YanNick. It sends evaluated skin-bone poses and model updates to the separately distributed UE integration on the same Windows computer.

## Requirements

Windows 64-bit; Blender 5.0-5.2 (tested 5.0.1, 5.1.2 and 5.2.0). The matching UE integration is required for Unreal Engine previews and is not included in this repository. No character models, animations, Blender or Unreal Engine installation is included.

## Install

Download the [installable Blender extension ZIP](https://github.com/lelenwan/Blender-UE-Live-Link-Companion/raw/refs/heads/main/blender_ue_live_link-0.6.5.zip). In Blender Preferences, choose Install from Disk from the extensions/add-ons menu, select the ZIP and enable Blender UE Live Link. Open the UE project with its Live Link integration enabled, select that running project in Blender, choose the skinned character, Sync Model, and start Live Link.

IK controllers remain in Blender. The extension sends evaluated deform-bone motion. It does not automatically record a UE Animation Sequence, generate animation, or stream morph targets or cloth.

## Source and license

The installable ZIP contains the Python source. The same files are available under `extension/`. Distributed under GPL-3.0-or-later; see COPYING.txt and NOTICE.txt. The originally packaged bridge attributed its Blender component to Kimodo; the retained notice documents this provenance. Current maintenance does not remove applicable upstream rights.

This repository does not contain the UE integration or apply GPL to Unreal Engine.

Support: 16759624@qq.com
