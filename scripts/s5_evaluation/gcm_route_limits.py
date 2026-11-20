"""Channel Studio GCM Rev.15 表4-2、§13.2.1：按输入的米制笛卡尔坐标复核。"""
import math


def route_limits(frame_ids, base, mobile, frequency_hz):
    if not frame_ids or len(base) != len(frame_ids) or len(mobile) != len(frame_ids):
        raise ValueError("每个时刻必须同时提供基站和移动端位置")
    if len(set(frame_ids)) != len(frame_ids):
        raise ValueError("帧编号重复")
    if not math.isfinite(frequency_hz) or frequency_hz <= 0:
        raise ValueError("载频必须是有限正数")
    points = [*base, *mobile]
    if any(len(p) != 3 or not all(math.isfinite(x) for x in p) for p in points):
        raise ValueError("每个位置必须包含三个有限的米制坐标")
    distances = [math.dist(a, b) for a, b in zip(mobile, mobile[1:])]
    segments = list(zip(frame_ids, frame_ids[1:], distances))
    max_axis = max(abs(x) for p in points for x in p)
    max_radius = max(math.hypot(*p) for p in points)
    max_link = max(math.dist(a, b) for a, b in zip(base, mobile))
    length = math.fsum(distances)
    minimum_length = 25 * 299792458 / frequency_hz
    return dict(position_count=len(frame_ids), last_frame=frame_ids[-1],
                segment_count=len(segments), max_segment_m=max(distances, default=None),
                segments=[dict(from_frame=a, to_frame=b, distance_m=d) for a, b, d in segments],
                max_abs_coordinate_m=max_axis, max_origin_distance_m=max_radius,
                max_link_distance_m=max_link, axis_limits_ok=max_axis <= 100000,
                origin_distance_ok=max_radius < 100000, link_distance_ok=max_link < 100000,
                min_segment_m=min(distances, default=None), length_m=length,
                cluster_spacing_ok=all(d >= 0.3 for d in distances),
                cluster_short_segments=[[a, b] for a, b, d in segments if d < 0.3],
                general_editor_short_segments=[[a, b] for a, b, d in segments if d < 1],
                minimum_route_length_m=minimum_length,
                cluster_length_ok=len(frame_ids) == 1 or length >= minimum_length,
                preserves_all_positions_by_count=len(frame_ids) <= 500)
