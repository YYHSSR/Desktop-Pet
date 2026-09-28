#ifndef PET_CORE_H
#define PET_CORE_H

#include <stdint.h>

#ifdef _WIN32
#  ifdef PET_CORE_BUILD
#    define PET_API __declspec(dllexport)
#  else
#    define PET_API __declspec(dllimport)
#  endif
#else
#  define PET_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

enum { PET_ABI_VERSION = 2, PET_OK = 0, PET_INVALID_INPUT = 1,
       PET_INSUFFICIENT_CAPACITY = 2, PET_INTERNAL_ERROR = 3, PET_ABI_MISMATCH = 4 };
enum { PET_MAX_MEMBERS = 512, PET_MAX_CIRCLES = 8192,
       PET_MAX_PAIRS = 130816, PET_MAX_SEPARATION_ITERATIONS = 64 };
/* Finite scalar inputs must have absolute value <= 1e12. A positive mass
   must be >= 1e-12; zero or negative mass keeps the historical zero-inverse-
   mass behavior. Pair history must be < UINT32_MAX so increment cannot wrap. */

/* All buffers are caller-owned and valid only for the duration of the call.
   Output capacity is checked before any output element is written. */
typedef struct PetCircle { double x, y, r; } PetCircle;
typedef struct PetMember {
    uint32_t struct_size, flags, circle_start, circle_count;
    uint32_t infinite_mass, reserved;
    double x, y, rx, ry, vx, vy, mass;
} PetMember;
typedef struct PetPairInput {
    uint32_t struct_size, a, b, history, ignored, swept, sort_rank;
    double fallback_nx, fallback_ny;
    double swept_nx, swept_ny, swept_overlap, swept_cx, swept_cy;
} PetPairInput;
typedef struct PetOptions {
    uint32_t struct_size, max_separation_iterations;
    int64_t tick;
    double restitution, friction, impulse_cap;
} PetOptions;
typedef struct PetPairOutput {
    uint32_t struct_size, pair_index, history, flags;
    double nx, ny, j, sep, contact_x, contact_y;
    double ax, ay, bx, by;
    double dvx_a, dvy_a, dvx_b, dvy_b;
    double dx_a, dy_a, dx_b, dy_b;
} PetPairOutput;
typedef struct PetMemberOutput {
    uint32_t struct_size, reserved;
    double dvx, dvy, dx, dy;
} PetMemberOutput;
typedef struct PetSolveRequest {
    uint32_t struct_size, member_count, circle_count, pair_count;
    const PetMember* members;
    const PetCircle* circles;
    const PetPairInput* pairs;
    const PetOptions* options;
} PetSolveRequest;
typedef struct PetSolveOutput {
    uint32_t struct_size, pair_capacity, member_capacity, pair_count;
    PetPairOutput* pairs;
    PetMemberOutput* members;
} PetSolveOutput;

PET_API uint32_t pet_core_abi_version(void);
/* UTF-8 static string owned by the DLL; never free it from Python. */
PET_API const char* pet_core_build_id(void);
/* Returns count 8 on success, 0 if capacity is insufficient. */
PET_API uint32_t pet_core_layout_sizes(uint32_t* sizes, uint32_t capacity);
PET_API uint32_t pet_core_layout_alignments(uint32_t* alignments, uint32_t capacity);
/* The offsets are ordered by the documented ctypes field order, with one
   entry per field. Returns the required count when capacity is insufficient. */
PET_API uint32_t pet_core_layout_offsets(uint32_t* offsets, uint32_t capacity);
PET_API int32_t pet_solve_collisions(const PetSolveRequest* request,
                                    PetSolveOutput* output,
                                    char* error_utf8, uint32_t error_capacity);

#ifdef __cplusplus
}
#endif
#endif
