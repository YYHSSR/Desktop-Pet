#include "collision_internal.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

namespace {
constexpr uint32_t visible = 1u << 0;
constexpr uint32_t paused = 1u << 8;
constexpr uint32_t enabled = 1u << 9;
constexpr double min_approach_speed = 80.0;

struct Contact {
    bool collided = false;
    double nx = 0, ny = 0, overlap = 0, cx = 0, cy = 0;
};
struct Separation {
    double sep = 0, dxa = 0, dya = 0, dxb = 0, dyb = 0;
};
struct Impulse {
    double j = 0, dvx_a = 0, dvy_a = 0, dvx_b = 0, dvy_b = 0;
};
struct Position { double x, y; };
struct WorkPair {
    uint32_t source, a, b, consecutive;
    bool swept, force_full = false;
    Contact contact;
    Impulse impulse;
    Separation separation;
};
struct Overlap {
    double depth, nx, ny;
    uint32_t work_index;
};

double inv_mass(const PetMember& member) {
    return member.infinite_mass || member.mass <= 0 ? 0.0 : 1.0 / member.mass;
}

Contact check_ellipse(const PetMember& a, const PetMember& b,
                      const PetPairInput& pair, Position ap, Position bp) {
    const double rx1 = std::max(1e-4, a.rx), ry1 = std::max(1e-4, a.ry);
    const double rx2 = std::max(1e-4, b.rx), ry2 = std::max(1e-4, b.ry);
    const double dx = bp.x - ap.x, dy = bp.y - ap.y;
    const double rx_sum = rx1 + rx2, ry_sum = ry1 + ry2;
    if (std::abs(dx) >= rx_sum || std::abs(dy) >= ry_sum) return {};
    const double ndx = dx / rx_sum, ndy = dy / ry_sum;
    const double ndist_sq = ndx * ndx + ndy * ndy;
    if (ndist_sq >= 1.0) return {};
    double nx, ny, overlap;
    if (std::sqrt(ndist_sq) < 1e-6) {
        nx = pair.fallback_nx; ny = pair.fallback_ny;
        overlap = std::min(rx_sum, ry_sum);
    } else {
        const double distance = std::hypot(dx, dy);
        if (distance < 1e-6) {
            nx = pair.fallback_nx; ny = pair.fallback_ny;
        } else {
            nx = dx / distance; ny = dy / distance;
        }
        const double eff_r1 = std::hypot(rx1 * nx, ry1 * ny);
        const double eff_r2 = std::hypot(rx2 * nx, ry2 * ny);
        overlap = std::max(0.0, eff_r1 + eff_r2 - distance);
    }
    return {true, nx, ny, overlap, ap.x + nx * rx1, ap.y + ny * ry1};
}

Contact check_circles(const PetSolveRequest& request, const PetMember& a,
                      const PetMember& b, const PetPairInput& pair,
                      Position ap, Position bp) {
    if (std::abs(bp.x - ap.x) >= a.rx + b.rx ||
        std::abs(bp.y - ap.y) >= a.ry + b.ry) return {};
    Contact best;
    const double aoff_x = ap.x - a.x, aoff_y = ap.y - a.y;
    const double boff_x = bp.x - b.x, boff_y = bp.y - b.y;
    for (uint32_t i = 0; i < a.circle_count; ++i) {
        const auto& ac = request.circles[a.circle_start + i];
        const double x1 = ac.x + aoff_x, y1 = ac.y + aoff_y;
        const double r1 = std::max(1e-4, ac.r);
        for (uint32_t j = 0; j < b.circle_count; ++j) {
            const auto& bc = request.circles[b.circle_start + j];
            const double x2 = bc.x + boff_x, y2 = bc.y + boff_y;
            const double r2 = std::max(1e-4, bc.r);
            const double dx = x2 - x1, dy = y2 - y1;
            const double distance = std::hypot(dx, dy);
            if (distance >= r1 + r2) continue;
            const double nx = distance < 1e-6 ? pair.fallback_nx : dx / distance;
            const double ny = distance < 1e-6 ? pair.fallback_ny : dy / distance;
            const double depth = r1 + r2 - distance;
            // UCRT hypot may differ from Python math.hypot by one ULP for
            // translated, geometrically tied circles. Preserve the first
            // contact on such numerical ties, as the reference loop does.
            const double tie_tolerance = 4.0 * std::numeric_limits<double>::epsilon() *
                std::max({1.0, std::abs(depth), std::abs(best.overlap)});
            if (!best.collided || depth > best.overlap + tie_tolerance) {
                best = {true, nx, ny, depth,
                    (x1 + nx * r1 + x2 - nx * r2) / 2.0,
                    (y1 + ny * r1 + y2 - ny * r2) / 2.0};
            }
        }
    }
    return best;
}

Contact check_members(const PetSolveRequest& request, const PetPairInput& pair,
                      Position ap, Position bp) {
    const auto& a = request.members[pair.a];
    const auto& b = request.members[pair.b];
    if (a.circle_start != UINT32_MAX && b.circle_start != UINT32_MAX) {
        return check_circles(request, a, b, pair, ap, bp);
    }
    return check_ellipse(a, b, pair, ap, bp);
}

Impulse solve_impulse(const PetMember& a, const PetMember& b, const Contact& c,
                      const PetOptions& options) {
    const double inv_a = inv_mass(a), inv_b = inv_mass(b);
    if (inv_a == 0 && inv_b == 0) return {};
    const double vrx = b.vx - a.vx, vry = b.vy - a.vy;
    const double vn = vrx * c.nx + vry * c.ny;
    if (vn >= 0) return {};
    double e = std::max(0.0, std::min(1.0, options.restitution));
    if (a.infinite_mass || b.infinite_mass) {
        e = 0.0;
    }
    if (vn >= -min_approach_speed) e = 0.0;
    const double inv_sum = inv_a + inv_b;
    double jn = -(1.0 + e) * vn / inv_sum;
    const double max_inv = std::max(inv_a, inv_b);
    const double max_j = max_inv > 0 ? options.impulse_cap / max_inv : options.impulse_cap;
    jn = std::min(jn, max_j);
    const double tx = -c.ny, ty = c.nx;
    const double vt = vrx * tx + vry * ty;
    double jt = 0;
    if (std::abs(vt) > 1e-6 && options.friction > 0) {
        const double ideal = -vt / inv_sum;
        const double mu_max = options.friction * std::abs(jn);
        jt = std::max(-mu_max, std::min(mu_max, ideal));
    }
    const double jx = jn * c.nx + jt * tx;
    const double jy = jn * c.ny + jt * ty;
    return {jn, -jx * inv_a, -jy * inv_a, jx * inv_b, jy * inv_b};
}

Separation separate(double overlap, double nx, double ny,
                    double inv_a, double inv_b, bool force_full) {
    const double inv_sum = inv_a + inv_b;
    if (inv_sum <= 0) return {};
    const double effective = std::max(0.0, overlap - 0.5);
    if (effective <= 0 && !force_full) return {};
    const double distance = force_full ? std::min(overlap, 48.0) :
        std::max(1.0, std::min(12.0, effective * 0.6));
    const double fraction_a = inv_a / inv_sum, fraction_b = inv_b / inv_sum;
    return {distance, -nx * distance * fraction_a, -ny * distance * fraction_a,
            nx * distance * fraction_b, ny * distance * fraction_b};
}
}

namespace pet {
int solve(const PetSolveRequest& request, PetSolveOutput& output) {
    const auto& options = *request.options;
    std::vector<WorkPair> work;
    work.reserve(request.pair_count);
    for (uint32_t index = 0; index < request.pair_count; ++index) {
        const auto& pair = request.pairs[index];
        const auto& a = request.members[pair.a];
        const auto& b = request.members[pair.b];
        if (!(a.flags & visible) || !(b.flags & visible) ||
            !(a.flags & enabled) || !(b.flags & enabled) ||
            (a.flags & paused) || (b.flags & paused)) continue;
        Contact contact = check_members(request, pair, {a.x, a.y}, {b.x, b.y});
        if (pair.ignored) continue;
        bool swept = false;
        if (!contact.collided && pair.swept) {
            contact = {true, pair.swept_nx, pair.swept_ny, pair.swept_overlap,
                       pair.swept_cx, pair.swept_cy};
            swept = true;
        }
        if (!contact.collided || contact.overlap < 0) continue;
        const uint32_t consecutive = pair.history + 1;
        Impulse impulse = solve_impulse(a, b, contact, options);
        if (consecutive >= 3) {
            const double inv_a = inv_mass(a), inv_b = inv_mass(b);
            const double inv_sum = inv_a + inv_b;
            const double vn = (b.vx - a.vx) * contact.nx +
                              (b.vy - a.vy) * contact.ny;
            if (inv_sum > 0 && vn < -min_approach_speed) {
                const double jn = -vn / inv_sum;
                impulse = {jn, -jn * contact.nx * inv_a, -jn * contact.ny * inv_a,
                            jn * contact.nx * inv_b, jn * contact.ny * inv_b};
            }
        }
        work.push_back({index, pair.a, pair.b, consecutive, swept, false,
                        contact, impulse, {}});
    }

    std::vector<Position> positions;
    std::vector<PetMemberOutput> member_results;
    positions.reserve(request.member_count);
    member_results.reserve(request.member_count);
    for (uint32_t i = 0; i < request.member_count; ++i) {
        positions.push_back({request.members[i].x, request.members[i].y});
        member_results.push_back({sizeof(PetMemberOutput), 0, 0, 0, 0, 0});
    }
    auto apply = [&](WorkPair& pair, const Separation& sep) {
        positions[pair.a].x += sep.dxa;
        positions[pair.a].y += sep.dya;
        positions[pair.b].x += sep.dxb;
        positions[pair.b].y += sep.dyb;
        member_results[pair.a].dx += sep.dxa;
        member_results[pair.a].dy += sep.dya;
        member_results[pair.b].dx += sep.dxb;
        member_results[pair.b].dy += sep.dyb;
        pair.separation = sep;
    };
    for (auto& pair : work) {
        if (!pair.swept) continue;
        const auto sep = separate(pair.contact.overlap, pair.contact.nx, pair.contact.ny,
                                  inv_mass(request.members[pair.a]),
                                  inv_mass(request.members[pair.b]), false);
        apply(pair, sep);
    }

    for (uint32_t iteration = 0; iteration < options.max_separation_iterations; ++iteration) {
        std::vector<Overlap> overlaps;
        for (uint32_t index = 0; index < work.size(); ++index) {
            const auto& pair = work[index];
            if (pair.swept) continue;
            const auto contact = check_members(request, request.pairs[pair.source],
                                               positions[pair.a], positions[pair.b]);
            if (contact.collided && contact.overlap > 0.5) {
                overlaps.push_back({contact.overlap, contact.nx, contact.ny, index});
            }
        }
        if (overlaps.empty()) break;
        std::sort(overlaps.begin(), overlaps.end(), [&](const Overlap& lhs, const Overlap& rhs) {
            if (lhs.depth != rhs.depth) return lhs.depth > rhs.depth;
            return request.pairs[work[lhs.work_index].source].sort_rank <
                   request.pairs[work[rhs.work_index].source].sort_rank;
        });
        for (const auto& overlap : overlaps) {
            auto& pair = work[overlap.work_index];
            const bool force_full = pair.consecutive >= 3;
            const auto sep = separate(overlap.depth, overlap.nx, overlap.ny,
                                      inv_mass(request.members[pair.a]),
                                      inv_mass(request.members[pair.b]), force_full);
            if (force_full) pair.force_full = true;
            apply(pair, sep);
        }
    }

    for (uint32_t index = 0; index < work.size(); ++index) {
        const auto& pair = work[index];
        const auto& a = request.members[pair.a];
        const auto& b = request.members[pair.b];
        const auto& c = pair.contact;
        const auto& j = pair.impulse;
        const auto& s = pair.separation;
        output.pairs[index] = {
            sizeof(PetPairOutput), pair.source, pair.force_full ? 0u : pair.consecutive, 0,
            c.nx, c.ny, j.j, s.sep, c.cx, c.cy,
            a.x, a.y, b.x, b.y,
            j.dvx_a, j.dvy_a, j.dvx_b, j.dvy_b,
            s.dxa, s.dya, s.dxb, s.dyb
        };
        member_results[pair.a].dvx += j.dvx_a;
        member_results[pair.a].dvy += j.dvy_a;
        member_results[pair.b].dvx += j.dvx_b;
        member_results[pair.b].dvy += j.dvy_b;
    }
    std::copy(member_results.begin(), member_results.end(), output.members);
    output.pair_count = static_cast<uint32_t>(work.size());
    return PET_OK;
}
}
