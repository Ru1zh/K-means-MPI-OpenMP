#pragma once
#include "core.hpp"
#include <algorithm>
#include <array>
#include <climits>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#ifdef KM_MPI
#include <mpi.h>
#include <omp.h>
#ifndef _OPENMP
#error "MPI executable requires OpenMP; supply the correct compiler flags"
#endif
#endif

namespace km {
// Encapsulate communication and lifecycle; the serial build uses local operations and shares the same algorithm flow.
// MPI calls are made only by the thread that initialized MPI and must not be called from OpenMP worker threads.
class Runtime {
public:
    int rank = 0, size = 1, nodes = 1;
    std::string library = "none";
    Runtime(int& argc, char**& argv) {
#ifdef KM_MPI
        int provided = 0;
        // FUNNELED allows OpenMP compute threads but requires MPI calls to be made by the initializing thread.
        MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &provided);
        MPI_Comm_rank(MPI_COMM_WORLD, &rank); MPI_Comm_size(MPI_COMM_WORLD, &size);
        if (provided < MPI_THREAD_FUNNELED) fail("MPI_THREAD_FUNNELED unavailable");
        char version[MPI_MAX_LIBRARY_VERSION_STRING]; int length = 0;
        MPI_Get_library_version(version, &length); library.assign(version, length);
        // Some implementations count the C terminator in the returned length.
        library.erase(std::find(library.begin(), library.end(), '\0'), library.end());
        MPI_Comm shared;
        // Choose one representative per shared-memory communicator and sum the representative count as the actual node count.
        MPI_Comm_split_type(MPI_COMM_WORLD, MPI_COMM_TYPE_SHARED, rank, MPI_INFO_NULL, &shared);
        int local_rank; MPI_Comm_rank(shared, &local_rank);
        int leader = local_rank == 0;
        MPI_Allreduce(&leader, &nodes, 1, MPI_INT, MPI_SUM, MPI_COMM_WORLD);
        MPI_Comm_free(&shared);
#else
        (void)argc; (void)argv;
#endif
    }
    ~Runtime() {
#ifdef KM_MPI
        MPI_Finalize();
#endif
    }
    [[noreturn]] void fail(const std::string& message) const {
        std::cerr << "rank " << rank << ": " << message << '\n';
#ifdef KM_MPI
        // A single process exiting would leave others blocked in collective calls, so errors abort the whole communicator.
        MPI_Abort(MPI_COMM_WORLD, 1);
#endif
        std::exit(1);
    }
    double time() const {
#ifdef KM_MPI
        return MPI_Wtime();
#else
        return wall_time();
#endif
    }
    void barrier() const {
#ifdef KM_MPI
        MPI_Barrier(MPI_COMM_WORLD);
#endif
    }
    double maximum(double value) const {
#ifdef KM_MPI
        double out; MPI_Allreduce(&value, &out, 1, MPI_DOUBLE, MPI_MAX, MPI_COMM_WORLD); return out;
#else
        return value;
#endif
    }
    double sum(double value) const {
#ifdef KM_MPI
        double out; MPI_Allreduce(&value, &out, 1, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD); return out;
#else
        return value;
#endif
    }
    std::uint64_t xor_hash(std::uint64_t value) const {
#ifdef KM_MPI
        std::uint64_t out; MPI_Allreduce(&value, &out, 1, MPI_UINT64_T, MPI_BXOR, MPI_COMM_WORLD); return out;
#else
        return value;
#endif
    }
    void broadcast(int& value) const {
#ifdef KM_MPI
        MPI_Bcast(&value, 1, MPI_INT, 0, MPI_COMM_WORLD);
#else
        (void)value;
#endif
    }
    void dimensions(Config& c) const {
#ifdef KM_MPI
        MPI_Bcast(&c.n, 1, MPI_INT64_T, 0, MPI_COMM_WORLD);
        MPI_Bcast(&c.d, 1, MPI_INT, 0, MPI_COMM_WORLD);
#else
        (void)c;
#endif
    }
    void broadcast(std::vector<double>& values) const {
#ifdef KM_MPI
        MPI_Bcast(values.data(), static_cast<int>(values.size()), MPI_DOUBLE, 0, MPI_COMM_WORLD);
#else
        (void)values;
#endif
    }
    // When all=true every process receives the result; otherwise only root does; SSE is reduced separately by the caller when needed.
    void reduce(Stats& stats, Stats& global, bool all) const {
#ifdef KM_MPI
        const int len = static_cast<int>(stats.sums.size()), k = static_cast<int>(stats.counts.size());
        if (all) {
            MPI_Allreduce(stats.sums.data(), global.sums.data(), len, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
            MPI_Allreduce(stats.counts.data(), global.counts.data(), k, MPI_INT64_T, MPI_SUM, MPI_COMM_WORLD);
        } else {
            MPI_Reduce(stats.sums.data(), global.sums.data(), len, MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD);
            MPI_Reduce(stats.counts.data(), global.counts.data(), k, MPI_INT64_T, MPI_SUM, 0, MPI_COMM_WORLD);
        }
#else
        (void)all; global.sums = stats.sums; global.counts = stats.counts;
#endif
    }
    std::vector<double> scatter(const std::vector<double>& full, const Config& c) const {
        const auto p = partition(c.n, rank, size);
        std::vector<double> local(elements(p.size, c.d));
#ifdef KM_MPI
        std::vector<int> lengths(size), offsets(size);
        // Scatterv lengths and displacements are in double elements, not samples or bytes.
        // read_data already enforces N*D<=INT_MAX, so the conversion to int is safe here.
        for (int r = 0; r < size; ++r) {
            const auto part = partition(c.n, r, size);
            lengths[r] = static_cast<int>(elements(part.size, c.d));
            offsets[r] = static_cast<int>(elements(part.first, c.d));
        }
        MPI_Scatterv(full.data(), lengths.data(), offsets.data(), MPI_DOUBLE,
                     local.data(), static_cast<int>(local.size()), MPI_DOUBLE, 0, MPI_COMM_WORLD);
#else
        local = full;
#endif
        return local;
    }
    std::vector<int> gather_labels(const std::vector<int>& local, Count n) const {
#ifdef KM_MPI
        // Only the small-data --dump path collects labels; normal large measurements reduce statistics only.
        std::vector<int> result(rank == 0 ? static_cast<std::size_t>(n) : 0);
        std::vector<int> lengths(size), offsets(size);
        for (int r = 0; r < size; ++r) {
            const auto p = partition(n, r, size);
            lengths[r] = static_cast<int>(p.size); offsets[r] = static_cast<int>(p.first);
        }
        MPI_Gatherv(local.data(), static_cast<int>(local.size()), MPI_INT, result.data(),
                    lengths.data(), offsets.data(), MPI_INT, 0, MPI_COMM_WORLD);
        return result;
#else
        (void)n; return local;
#endif
    }
    // After the kernel, collect local kernel + five phase originals; root receives them in rank order.
    std::vector<double> gather_profile(const std::array<double, 6>& local) const {
#ifdef KM_MPI
        std::vector<double> result(rank == 0 ? static_cast<std::size_t>(size) * local.size() : 0);
        MPI_Gather(local.data(), static_cast<int>(local.size()), MPI_DOUBLE,
                   result.data(), static_cast<int>(local.size()), MPI_DOUBLE, 0, MPI_COMM_WORLD);
        return result;
#else
        return {local.begin(), local.end()};
#endif
    }
    int configure_threads(int requested) const {
#ifdef KM_MPI
        // Disable dynamic team shrinking; if resource limits prevent any process from reaching the requested thread count, fail uniformly.
        omp_set_dynamic(0); omp_set_num_threads(requested);
        int observed = 0;
        #pragma omp parallel num_threads(requested)
        {
            #pragma omp single
            observed = omp_get_num_threads();
        }
        int bad = observed != requested, any_bad = 0;
        MPI_Allreduce(&bad, &any_bad, 1, MPI_INT, MPI_MAX, MPI_COMM_WORLD);
        if (any_bad) throw std::runtime_error("Actual OpenMP team size differs from requested threads");
        return observed;
#else
        return requested;
#endif
    }
};
}
