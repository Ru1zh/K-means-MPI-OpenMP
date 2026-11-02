#include "core.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <numeric>
#include <stdexcept>
#ifdef _OPENMP
#include <omp.h>
#endif

namespace km {
double wall_time() {
    return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
Stats::Stats(int k, int d) : sums(elements(k, d)), counts(k) {}
void Stats::clear() { std::fill(sums.begin(), sums.end(), 0); std::fill(counts.begin(), counts.end(), 0); sse = 0; }
Workspace::Workspace(const Config& c) {
    if (c.variant != "v3") return;
    // Leave 64 extra bytes at the end of each segment so adjacent thread buffers never share a 64-byte cache line.
    sum_stride = elements(c.k, c.d) + 8;
    count_stride = static_cast<std::size_t>(c.k) + 8;
    const auto limit = std::numeric_limits<std::size_t>::max() / sizeof(double) / c.threads;
    if (sum_stride > limit || count_stride > limit) throw std::runtime_error("Thread buffer size overflow");
    sums.resize(sum_stride * c.threads); counts.resize(count_stride * c.threads);
}
namespace {
int nearest(const double* x, const std::vector<double>& centers, int k, int d, double& best) {
    int label = 0;
    best = std::numeric_limits<double>::infinity();
    for (int group = 0; group < k; ++group) {
        double distance = 0;
        const double* c = centers.data() + static_cast<std::size_t>(group) * d;
        for (int j = 0; j < d; ++j) { const double delta = x[j] - c[j]; distance += delta * delta; }
        // Traverse clusters in increasing index order and accept only strictly smaller distances; exact ties keep the lowest index.
        if (distance < best) { best = distance; label = group; }
    }
    return label;
}
}
void accumulate(const std::vector<double>& data, const std::vector<double>& centers,
                const Config& c, Workspace& work, Stats& stats, bool objective,
                std::vector<int>* labels, Phases* phases) {
    const double start = phases ? wall_time() : 0;
    stats.clear();
    const Count n = static_cast<Count>(data.size() / c.d);
    if (labels) labels->resize(static_cast<std::size_t>(n));
    const bool atomic = c.variant == "v2", local = c.variant == "v3";
    if (local) { std::fill(work.sums.begin(), work.sums.end(), 0); std::fill(work.counts.begin(), work.counts.end(), 0); }
    double sse = 0;
    int invalid = 0;
#ifdef _OPENMP
    // Dense Lloyd computes K distances per sample and uses static allocation; V0/V1 run serially only.
    // SSE sums and the error flag are combined via reduction; no exception is thrown inside a thread.
    #pragma omp parallel for schedule(static) num_threads(c.threads) if(atomic || local) reduction(+:sse) reduction(|:invalid)
#endif
    for (Count i = 0; i < n; ++i) {
        double distance;
        const double* x = data.data() + static_cast<std::size_t>(i) * c.d;
        const int group = nearest(x, centers, c.k, c.d, distance);
        if (!std::isfinite(distance)) { invalid = 1; continue; }
        if (labels) (*labels)[static_cast<std::size_t>(i)] = group;
        if (objective) sse += distance;
        if (atomic) {
            // V2: counts and every coordinate sum can be updated by multiple threads, so each must be protected.
#ifdef _OPENMP
            #pragma omp atomic update
#endif
            stats.counts[group] += 1;
            for (int j = 0; j < c.d; ++j) {
#ifdef _OPENMP
                #pragma omp atomic update
#endif
                stats.sums[static_cast<std::size_t>(group) * c.d + j] += x[j];
            }
        } else {
            // V3 writes to the calling thread's private buffer; V0/V1 write directly to the process statistics array.
            int tid = 0;
#ifdef _OPENMP
            if (local) tid = omp_get_thread_num();
#endif
            double* sums = local ? work.sums.data() + tid * work.sum_stride : stats.sums.data();
            Count* counts = local ? work.counts.data() + tid * work.count_stride : stats.counts.data();
            ++counts[group];
            for (int j = 0; j < c.d; ++j) sums[static_cast<std::size_t>(group) * c.d + j] += x[j];
        }
    }
    // Report errors after the parallel region; MPI_Abort in main terminates other processes waiting in collective calls.
    if (invalid || !std::isfinite(sse)) throw std::runtime_error("Nonfinite distance or objective (rescale input)");
    stats.sse = sse;
    const double merge_start = phases ? wall_time() : 0;
    if (phases) phases->accumulate += merge_start - start;
    if (local) {
        // Merge in fixed thread order after the implicit barrier; a different thread count can still change floating-point rounding order.
        for (int t = 0; t < c.threads; ++t) {
            for (std::size_t j = 0; j < stats.sums.size(); ++j) stats.sums[j] += work.sums[t * work.sum_stride + j];
            for (int k = 0; k < c.k; ++k) stats.counts[k] += work.counts[t * work.count_stride + k];
        }
    }
    if (phases) phases->merge += wall_time() - merge_start;
}
void check_stats(const Stats& stats, Count n, bool objective) {
    Count total = 0;
    for (auto value : stats.counts) {
        // Compare the remaining budget before adding, and check negatives, total overflow and integer overflow at the same time.
        if (value < 0 || value > n - total) throw std::runtime_error("Invalid cluster counts");
        total += value;
    }
    if (total != n) throw std::runtime_error("Cluster counts do not sum to N");
    for (double value : stats.sums) if (!std::isfinite(value)) throw std::runtime_error("Nonfinite coordinate sum");
    if (objective && (!std::isfinite(stats.sse) || stats.sse < 0)) throw std::runtime_error("Invalid SSE");
}
double update(std::vector<double>& centers, const Stats& stats, const Config& c) {
    check_stats(stats, c.n, false);
    double max_move = 0, max_norm = 0;
    for (int k = 0; k < c.k; ++k) {
        double movement = 0, norm = 0;
        for (int d = 0; d < c.d; ++d) {
            const auto j = static_cast<std::size_t>(k) * c.d + d;
            const double old = centers[j];
            // Empty clusters keep their previous centroid to avoid division by zero and keep the update rule identical across variants.
            const double next = stats.counts[k] ? stats.sums[j] / static_cast<double>(stats.counts[k]) : old;
            // Accumulate the norm dimension by dimension with hypot to reduce intermediate overflow risk compared with direct squared sums.
            movement = std::hypot(movement, next - old);
            norm = std::hypot(norm, old);
            centers[j] = next;
        }
        max_move = std::max(max_move, movement); max_norm = std::max(max_norm, norm);
    }
    // Scale the relative displacement by the maximum norm of the old centroids; a floor of 1 prevents division by zero for zero centroids.
    const double delta = max_move / std::max(1.0, max_norm);
    if (!std::isfinite(delta)) throw std::runtime_error("Nonfinite centroid shift");
    return delta;
}
}
