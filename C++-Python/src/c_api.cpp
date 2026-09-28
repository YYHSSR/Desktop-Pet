#include "collision_internal.h"
#include "pet_build_id.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <vector>

namespace {
constexpr double scalar_limit = 1e12;
bool valid_scalar(double value) noexcept {
    return std::isfinite(value) && std::abs(value) <= scalar_limit;
}

void write_error(char* dst, uint32_t capacity, const char* message) noexcept {
    if (!dst || !capacity) return;
    const auto n = std::min<std::size_t>(std::strlen(message), capacity - 1);
    std::memcpy(dst, message, n);
    dst[n] = '\0';
}
}

extern "C" uint32_t pet_core_abi_version(void) { return PET_ABI_VERSION; }
extern "C" const char* pet_core_build_id(void) { return PET_BUILD_ID; }

extern "C" uint32_t pet_core_layout_sizes(uint32_t* sizes, uint32_t capacity) {
    if (!sizes || capacity < 8) return 0;
    const uint32_t actual[8] = {
        sizeof(PetCircle), sizeof(PetMember), sizeof(PetPairInput), sizeof(PetOptions),
        sizeof(PetPairOutput), sizeof(PetMemberOutput), sizeof(PetSolveRequest), sizeof(PetSolveOutput)
    };
    std::memcpy(sizes, actual, sizeof(actual));
    return 8;
}

extern "C" uint32_t pet_core_layout_alignments(uint32_t* alignments, uint32_t capacity) {
    if (!alignments || capacity < 8) return 0;
    const uint32_t actual[8] = {
        alignof(PetCircle), alignof(PetMember), alignof(PetPairInput), alignof(PetOptions),
        alignof(PetPairOutput), alignof(PetMemberOutput),
        alignof(PetSolveRequest), alignof(PetSolveOutput)
    };
    std::memcpy(alignments, actual, sizeof(actual));
    return 8;
}

extern "C" uint32_t pet_core_layout_offsets(uint32_t* offsets, uint32_t capacity) {
#define FIELD(type, name) static_cast<uint32_t>(offsetof(type, name))
    const uint32_t actual[] = {
        FIELD(PetCircle, x), FIELD(PetCircle, y), FIELD(PetCircle, r),
        FIELD(PetMember, struct_size), FIELD(PetMember, flags),
        FIELD(PetMember, circle_start), FIELD(PetMember, circle_count),
        FIELD(PetMember, infinite_mass), FIELD(PetMember, reserved),
        FIELD(PetMember, x), FIELD(PetMember, y), FIELD(PetMember, rx),
        FIELD(PetMember, ry), FIELD(PetMember, vx), FIELD(PetMember, vy), FIELD(PetMember, mass),
        FIELD(PetPairInput, struct_size), FIELD(PetPairInput, a), FIELD(PetPairInput, b),
        FIELD(PetPairInput, history), FIELD(PetPairInput, ignored),
        FIELD(PetPairInput, swept), FIELD(PetPairInput, sort_rank),
        FIELD(PetPairInput, fallback_nx), FIELD(PetPairInput, fallback_ny),
        FIELD(PetPairInput, swept_nx), FIELD(PetPairInput, swept_ny),
        FIELD(PetPairInput, swept_overlap), FIELD(PetPairInput, swept_cx), FIELD(PetPairInput, swept_cy),
        FIELD(PetOptions, struct_size), FIELD(PetOptions, max_separation_iterations),
        FIELD(PetOptions, tick), FIELD(PetOptions, restitution),
        FIELD(PetOptions, friction), FIELD(PetOptions, impulse_cap),
        FIELD(PetPairOutput, struct_size), FIELD(PetPairOutput, pair_index),
        FIELD(PetPairOutput, history), FIELD(PetPairOutput, flags),
        FIELD(PetPairOutput, nx), FIELD(PetPairOutput, ny), FIELD(PetPairOutput, j),
        FIELD(PetPairOutput, sep), FIELD(PetPairOutput, contact_x), FIELD(PetPairOutput, contact_y),
        FIELD(PetPairOutput, ax), FIELD(PetPairOutput, ay), FIELD(PetPairOutput, bx), FIELD(PetPairOutput, by),
        FIELD(PetPairOutput, dvx_a), FIELD(PetPairOutput, dvy_a),
        FIELD(PetPairOutput, dvx_b), FIELD(PetPairOutput, dvy_b),
        FIELD(PetPairOutput, dx_a), FIELD(PetPairOutput, dy_a),
        FIELD(PetPairOutput, dx_b), FIELD(PetPairOutput, dy_b),
        FIELD(PetMemberOutput, struct_size), FIELD(PetMemberOutput, reserved),
        FIELD(PetMemberOutput, dvx), FIELD(PetMemberOutput, dvy),
        FIELD(PetMemberOutput, dx), FIELD(PetMemberOutput, dy),
        FIELD(PetSolveRequest, struct_size), FIELD(PetSolveRequest, member_count),
        FIELD(PetSolveRequest, circle_count), FIELD(PetSolveRequest, pair_count),
        FIELD(PetSolveRequest, members), FIELD(PetSolveRequest, circles),
        FIELD(PetSolveRequest, pairs), FIELD(PetSolveRequest, options),
        FIELD(PetSolveOutput, struct_size), FIELD(PetSolveOutput, pair_capacity),
        FIELD(PetSolveOutput, member_capacity), FIELD(PetSolveOutput, pair_count),
        FIELD(PetSolveOutput, pairs), FIELD(PetSolveOutput, members),
    };
#undef FIELD
    constexpr uint32_t count = static_cast<uint32_t>(sizeof(actual) / sizeof(actual[0]));
    if (!offsets || capacity < count) return count;
    std::memcpy(offsets, actual, sizeof(actual));
    return count;
}

extern "C" int32_t pet_solve_collisions(const PetSolveRequest* request,
                                         PetSolveOutput* output,
                                         char* error_utf8, uint32_t error_capacity) {
    write_error(error_utf8, error_capacity, "");
    try {
        if (output && output->struct_size == sizeof(PetSolveOutput)) output->pair_count = 0;
        if (!request || !output || !request->options) {
            write_error(error_utf8, error_capacity, "null request, output or options");
            return PET_INVALID_INPUT;
        }
        if (request->struct_size != sizeof(PetSolveRequest) ||
            output->struct_size != sizeof(PetSolveOutput) ||
            request->options->struct_size != sizeof(PetOptions)) {
            write_error(error_utf8, error_capacity, "ABI structure size mismatch");
            return PET_ABI_MISMATCH;
        }
        if (request->member_count > PET_MAX_MEMBERS ||
            request->circle_count > PET_MAX_CIRCLES ||
            request->pair_count > PET_MAX_PAIRS ||
            request->options->max_separation_iterations > PET_MAX_SEPARATION_ITERATIONS) {
            write_error(error_utf8, error_capacity, "count or iteration limit exceeded");
            return PET_INVALID_INPUT;
        }
        const auto& opt = *request->options;
        if (!valid_scalar(opt.restitution) || !valid_scalar(opt.friction) ||
            !valid_scalar(opt.impulse_cap)) {
            write_error(error_utf8, error_capacity, "invalid nonfinite or excessive option");
            return PET_INVALID_INPUT;
        }
        if ((request->member_count && !request->members) ||
            (request->circle_count && !request->circles) ||
            (request->pair_count && !request->pairs)) {
            write_error(error_utf8, error_capacity, "null input buffer");
            return PET_INVALID_INPUT;
        }
        if (output->member_capacity < request->member_count ||
            output->pair_capacity < request->pair_count ||
            (request->member_count && !output->members) ||
            (request->pair_count && !output->pairs)) {
            output->pair_count = request->pair_count;
            write_error(error_utf8, error_capacity, "output capacity too small");
            return PET_INSUFFICIENT_CAPACITY;
        }
        for (uint32_t i = 0; i < request->member_count; ++i) {
            const auto& m = request->members[i];
            if (m.struct_size != sizeof(PetMember) ||
                (m.circle_start == UINT32_MAX && m.circle_count != 0) ||
                (m.circle_start != UINT32_MAX &&
                 (m.circle_start > request->circle_count || m.circle_count > request->circle_count - m.circle_start))) {
                write_error(error_utf8, error_capacity, "invalid member layout or circle range");
                return PET_INVALID_INPUT;
            }
            if (!valid_scalar(m.x) || !valid_scalar(m.y) ||
                !valid_scalar(m.rx) || !valid_scalar(m.ry) ||
                !valid_scalar(m.vx) || !valid_scalar(m.vy) ||
                !valid_scalar(m.mass) || (m.mass > 0 && m.mass < 1e-12)) {
                write_error(error_utf8, error_capacity, "invalid nonfinite or excessive member value");
                return PET_INVALID_INPUT;
            }
        }
        for (uint32_t i = 0; i < request->circle_count; ++i) {
            const auto& c = request->circles[i];
            if (!valid_scalar(c.x) || !valid_scalar(c.y) || !valid_scalar(c.r)) {
                write_error(error_utf8, error_capacity, "invalid nonfinite or excessive circle value");
                return PET_INVALID_INPUT;
            }
        }
        std::vector<uint8_t> rank_seen(request->pair_count, 0);
        for (uint32_t i = 0; i < request->pair_count; ++i) {
            const auto& p = request->pairs[i];
            if (p.struct_size != sizeof(PetPairInput) || p.a >= request->member_count ||
                p.b >= request->member_count || p.a >= p.b || p.history == UINT32_MAX ||
                p.sort_rank >= request->pair_count || rank_seen[p.sort_rank]) {
                write_error(error_utf8, error_capacity, "invalid pair layout or member index");
                return PET_INVALID_INPUT;
            }
            rank_seen[p.sort_rank] = 1;
            if (!valid_scalar(p.fallback_nx) || !valid_scalar(p.fallback_ny) ||
                !valid_scalar(p.swept_nx) || !valid_scalar(p.swept_ny) ||
                !valid_scalar(p.swept_overlap) || !valid_scalar(p.swept_cx) ||
                !valid_scalar(p.swept_cy)) {
                write_error(error_utf8, error_capacity, "invalid nonfinite or excessive pair value");
                return PET_INVALID_INPUT;
            }
        }
        return pet::solve(*request, *output);
    } catch (const std::exception& exc) {
        write_error(error_utf8, error_capacity, exc.what());
        return PET_INTERNAL_ERROR;
    } catch (...) {
        write_error(error_utf8, error_capacity, "unknown native exception");
        return PET_INTERNAL_ERROR;
    }
}
