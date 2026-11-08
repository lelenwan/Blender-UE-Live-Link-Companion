import json
import math
from numbers import Real


PROTOCOL_VERSION = 1
MAX_PACKET_BYTES = 60 * 1024
TRANSFORM_COMPONENT_COUNT = 10
QUATERNION_EPSILON = 1e-12


class ProtocolError(ValueError):
    pass


def _validate_subject(subject):
    if not isinstance(subject, str) or not subject.strip():
        raise ProtocolError("subject must be a non-empty string")


def _validate_sequence(sequence):
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise ProtocolError("sequence must be a non-negative integer")


def _finite_number(value, field_name):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ProtocolError(f"{field_name} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ProtocolError(f"{field_name} must be finite")
    return converted


def _encode_packet(packet):
    try:
        encoded = json.dumps(
            packet,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"packet cannot be encoded: {exc}") from exc

    if len(encoded) > MAX_PACKET_BYTES:
        raise ProtocolError("encoded packet exceeds the 60 KiB limit")
    return encoded


def validate_skeleton(bone_names, bone_parents):
    if not bone_names:
        raise ProtocolError("skeleton must contain at least one bone")
    if len(bone_names) != len(bone_parents):
        raise ProtocolError("bone name and parent arrays must have equal lengths")

    seen_names = set()
    root_count = 0
    for index, (name, parent_index) in enumerate(zip(bone_names, bone_parents)):
        if not isinstance(name, str) or not name:
            raise ProtocolError(f"bone name at index {index} must be non-empty")
        if name in seen_names:
            raise ProtocolError(f"duplicate bone name: {name}")
        seen_names.add(name)

        if isinstance(parent_index, bool) or not isinstance(parent_index, int):
            raise ProtocolError(f"parent index for {name} must be an integer")
        if parent_index == -1:
            root_count += 1
            if index != 0:
                raise ProtocolError("the root bone must be first")
        elif parent_index < 0 or parent_index >= index:
            raise ProtocolError(f"invalid parent index for {name}: {parent_index}")

    if root_count != 1:
        raise ProtocolError("skeleton must contain exactly one root")


def encode_skeleton(subject, sequence, bone_names, bone_parents):
    _validate_subject(subject)
    _validate_sequence(sequence)
    validate_skeleton(bone_names, bone_parents)
    return _encode_packet(
        {
            "version": PROTOCOL_VERSION,
            "type": "skeleton",
            "subject": subject,
            "sequence": sequence,
            "bone_names": list(bone_names),
            "bone_parents": list(bone_parents),
        }
    )


def _normalize_transform(transform, transform_index):
    if len(transform) != TRANSFORM_COMPONENT_COUNT:
        raise ProtocolError(
            f"transform {transform_index} must contain "
            f"{TRANSFORM_COMPONENT_COUNT} values"
        )

    values = [
        _finite_number(value, f"transform {transform_index} value {value_index}")
        for value_index, value in enumerate(transform)
    ]
    quaternion_norm = math.sqrt(sum(component * component for component in values[3:7]))
    if quaternion_norm <= QUATERNION_EPSILON:
        raise ProtocolError(f"transform {transform_index} quaternion is not normalizable")
    values[3:7] = [component / quaternion_norm for component in values[3:7]]
    return values


def encode_frame(subject, sequence, time_seconds, transforms):
    _validate_subject(subject)
    _validate_sequence(sequence)
    normalized_time = _finite_number(time_seconds, "time_seconds")
    if not transforms:
        raise ProtocolError("frame must contain at least one transform")

    normalized_transforms = [
        _normalize_transform(transform, index)
        for index, transform in enumerate(transforms)
    ]
    return _encode_packet(
        {
            "version": PROTOCOL_VERSION,
            "type": "frame",
            "subject": subject,
            "sequence": sequence,
            "time_seconds": normalized_time,
            "transforms": normalized_transforms,
        }
    )
