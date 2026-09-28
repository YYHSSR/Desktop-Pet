"""Benchmark fixtures must model the geometry named in the report."""

from scripts.bench_collision_backends import scene
from pet import collision


def test_circle_chain_uses_each_members_world_coordinates():
    members = scene(3, "circles")
    for member in members:
        assert member.circles == [[member.x, member.y, 24], [member.x + 12, member.y, 12]]
        assert all(abs(cx - member.x) + radius <= member.radius_x + 12
                   for cx, _, radius in member.circles)
    assert members[0].circles != members[1].circles
    contact = collision.check_collision_circles(
        members[0].circles, members[1].circles,
        members[0].runtime_id, members[1].runtime_id,
    )
    assert contact[0]
    assert 0 <= contact[4] <= members[1].x + members[1].radius_x


def test_static_scene_sets_real_static_flag_only_on_wall():
    members = scene(3, "static")
    assert members[0].is_infinite_mass
    assert members[0].flags & collision.FLAG_STATIC
    assert all(not (member.flags & collision.FLAG_STATIC) for member in members[1:])
