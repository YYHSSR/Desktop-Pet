#include "pet_core.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

// These checks must execute in Release builds compiled with NDEBUG.
#define CHECK(expr) do { \
    if (!(expr)) { \
        std::fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #expr); \
        return 1; \
    } \
} while (false)

int main() {
    if (std::getenv("PET_CORE_TEST_INJECT_FAILURE")) {
        CHECK(1 == 2);  // Negative control for the Release CTest gate.
    }
    CHECK(pet_core_abi_version() == PET_ABI_VERSION);
    CHECK(std::strncmp(pet_core_build_id(), "collision-core/2.0+", 19) == 0);
    std::array<uint32_t, 8> sizes{};
    CHECK(pet_core_layout_sizes(sizes.data(), sizes.size()) == 8);
    CHECK(sizes[1] == sizeof(PetMember));
    CHECK(pet_core_layout_sizes(nullptr, sizes.size()) == 0);
    CHECK(pet_core_layout_sizes(sizes.data(), 7) == 0);
    std::array<uint32_t, 8> alignments{};
    CHECK(pet_core_layout_alignments(alignments.data(), alignments.size()) == 8);
    CHECK(alignments[1] == alignof(PetMember));
    const auto offset_count = pet_core_layout_offsets(nullptr, 0);
    CHECK(offset_count == 78);
    std::array<uint32_t, 78> offsets{};
    CHECK(pet_core_layout_offsets(offsets.data(), offsets.size()) == offsets.size());
    CHECK(offsets[3] == 0);  // PetMember.struct_size

    PetOptions options{sizeof(PetOptions), 4, 7, 0.82, 0.08, 9000};
    PetSolveRequest empty{sizeof(PetSolveRequest), 0, 0, 0, nullptr, nullptr, nullptr, &options};
    PetSolveOutput empty_out{sizeof(PetSolveOutput), 0, 0, 999, nullptr, nullptr};
    char error[128]{};
    CHECK(pet_solve_collisions(&empty, &empty_out, error, sizeof(error)) == PET_OK);
    CHECK(empty_out.pair_count == 0);
    CHECK(error[0] == '\0');
    CHECK(pet_solve_collisions(nullptr, &empty_out, error, sizeof(error)) == PET_INVALID_INPUT);
    CHECK(std::strstr(error, "null request") != nullptr);
    CHECK(pet_solve_collisions(&empty, nullptr, error, sizeof(error)) == PET_INVALID_INPUT);
    PetSolveRequest missing_options = empty;
    missing_options.options = nullptr;
    CHECK(pet_solve_collisions(&missing_options, &empty_out, error, sizeof(error)) == PET_INVALID_INPUT);
    PetSolveRequest wrong_request = empty;
    wrong_request.struct_size = 0;
    CHECK(pet_solve_collisions(&wrong_request, &empty_out, error, sizeof(error)) == PET_ABI_MISMATCH);
    PetOptions wrong_options = options;
    wrong_options.struct_size = 0;
    wrong_request = empty;
    wrong_request.options = &wrong_options;
    CHECK(pet_solve_collisions(&wrong_request, &empty_out, error, sizeof(error)) == PET_ABI_MISMATCH);
    PetSolveOutput wrong_output = empty_out;
    wrong_output.struct_size = 0;
    CHECK(pet_solve_collisions(&empty, &wrong_output, error, sizeof(error)) == PET_ABI_MISMATCH);

    PetMember members[2] = {
        {sizeof(PetMember), 513, UINT32_MAX, 0, 0, 0, 0, 0, 50, 50, 100, 0, 1},
        {sizeof(PetMember), 513, UINT32_MAX, 0, 0, 0, 70, 0, 50, 50, -100, 0, 1},
    };
    PetPairInput pair{sizeof(PetPairInput), 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0};
    PetSolveRequest request{sizeof(PetSolveRequest), 2, 0, 1, members, nullptr, &pair, &options};
    PetPairOutput pair_output{};
    PetMemberOutput member_output[2]{};
    PetSolveOutput output{sizeof(PetSolveOutput), 0, 2, 0, &pair_output, member_output};
    pair_output.pair_index = 0xABCDEF12;
    CHECK(pet_solve_collisions(&request, &output, error, sizeof(error)) == PET_INSUFFICIENT_CAPACITY);
    CHECK(output.pair_count == 1);
    CHECK(pair_output.pair_index == 0xABCDEF12);
    output.pair_capacity = 1;
    output.member_capacity = 1;
    CHECK(pet_solve_collisions(&request, &output, error, sizeof(error)) == PET_INSUFFICIENT_CAPACITY);
    CHECK(pair_output.pair_index == 0xABCDEF12);
    output.member_capacity = 2;
    CHECK(pet_solve_collisions(&request, &output, error, sizeof(error)) == PET_OK);
    CHECK(output.pair_count == 1);
    CHECK(std::strcmp(error, "") == 0);
    CHECK(pair_output.pair_index == 0);
    CHECK(pair_output.j > 0);
    CHECK(member_output[0].dvx < 0);
    CHECK(member_output[1].dvx > 0);
    CHECK(std::isfinite(pair_output.sep));
    PetOptions bad_options = options;
    bad_options.max_separation_iterations = PET_MAX_SEPARATION_ITERATIONS + 1;
    PetSolveRequest bad_request = request;
    bad_request.options = &bad_options;
    output.pair_count = 77;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    CHECK(output.pair_count == 0);
    bad_options = options;
    bad_options.restitution = std::numeric_limits<double>::quiet_NaN();
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    CHECK(output.pair_count == 0);

    bad_request = request;
    bad_request.members = nullptr;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    bad_request = request;
    bad_request.pairs = nullptr;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    PetMember bad_members[2] = {members[0], members[1]};
    bad_members[0].circle_start = 1;
    bad_members[0].circle_count = 1;
    bad_request = request;
    bad_request.members = bad_members;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    PetPairInput bad_pair = pair;
    bad_pair.b = 2;
    bad_request = request;
    bad_request.pairs = &bad_pair;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);
    bad_pair = pair;
    bad_pair.history = UINT32_MAX;
    CHECK(pet_solve_collisions(&bad_request, &output, error, sizeof(error)) == PET_INVALID_INPUT);

    char short_error[2] = {'X', 'Y'};
    CHECK(pet_solve_collisions(nullptr, &output, short_error, 1) == PET_INVALID_INPUT);
    CHECK(short_error[0] == '\0' && short_error[1] == 'Y');
    std::puts("pet_core Release checks passed");
    return 0;
}
