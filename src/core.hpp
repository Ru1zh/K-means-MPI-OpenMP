#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace km {
// Global sample counts and cluster counts use 64-bit integers throughout, matching MPI_INT64_T.
using Count = std::int64_t;
struct Config {
    Count n = 10000;
    int d = 8, k = 16, threads = 1, iterations = 50, warmup = 0;
    std::uint64_t seed = 42;
    double tol = 1e-6;
    std::string variant = "v0", comm = "allreduce", mode = "fixed";
    std::string input, init_spec;
    bool skew = false, dump = false, trace = false, profile = false, help = false;
};
// The global sample range owned by this process is [first, first + size); size may be zero.
struct Partition { Count first, size; };
struct Stats {
    // Sufficient statistics per cluster: sums[k*D+j] is a coordinate sum and counts[k] is the membership count.
    // Reduce these statistics before computing means so unequal per-process cluster sizes are handled correctly.
    std::vector<double> sums;
    std::vector<Count> counts;
    double sse = 0;
    Stats(int k, int d);
    void clear();
};
struct Workspace {
    // Allocated only for V3; each thread locates its private buffer by stride to avoid synchronization inside the sample loop.
    std::vector<double> sums;
    std::vector<Count> counts;
    std::size_t sum_stride = 0, count_stride = 0;
    explicit Workspace(const Config& c);
};
struct Phases { double accumulate = 0, merge = 0, reduce = 0, update = 0, control = 0; };
Config parse(int argc, char** argv, bool parallel);
void validate(const Config& c);
std::size_t elements(Count n, int d);
Partition partition(Count n, int rank, int size);
std::vector<double> read_data(const std::string& path, Count& n, int& d);
std::vector<double> generate(const Config& c, Partition p);
std::vector<Count> initial_indices(const Config& c);
std::vector<double> initial_centers(const Config& c, const std::vector<Count>& ids,
                                    const std::vector<double>& full);
std::uint64_t fingerprint(const std::vector<double>& data, Count first, int d);
double wall_time();
// Each call clears and recomputes local statistics; objective/labels/phases are enabled on demand,
// Ordinary iterations do not need labels or accumulated SSE, which reduces extra work during performance measurement.
void accumulate(const std::vector<double>& data, const std::vector<double>& centers,
                const Config& c, Workspace& work, Stats& stats, bool objective,
                std::vector<int>* labels, Phases* phases);
// stats must cover the global N samples; update centroids in place and return the relative maximum centroid displacement.
double update(std::vector<double>& centers, const Stats& stats, const Config& c);
void check_stats(const Stats& stats, Count n, bool objective);
}
