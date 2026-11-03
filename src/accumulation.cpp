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
    // Use a process-local origin before conversion to double. Subtracting two
    // large epoch-valued doubles loses precision in very short phase timings.
    static const auto origin = std::chrono::steady_clock::now();
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - origin).count();
}
Stats::Stats(int k, int d) : sums(elements(k, d)), counts(k) {}
void Stats::clear() { std::fill(sums.begin(), sums.end(), 0); std::fill(counts.begin(), counts.end(), 0); sse = 0; }
Workspace::Workspace(const Config& c) {
    if (c.variant != "v3") return;
    // 每段末尾额外留出 64 字节，避免相邻线程缓冲边界落入同一条 64 字节缓存行。
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
        // 按簇编号递增遍历且只接受严格更小距离，完全等距时自然保留最小编号。
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
    // 稠密 Lloyd 每个样本都计算 K 个距离，使用 static 分配；V0/V1 仅串行执行。
    // SSE 求和和错误标志通过 reduction 汇合，线程内部不抛异常。
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
            // V2：计数与每个坐标和都可能被多个线程更新，必须分别保护。
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
            // V3 写当前线程的独立缓冲；V0/V1 则直接写进程统计数组。
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
    // 并行区域结束后统一报错，main 中的 MPI_Abort 会终止其他等待通信的进程。
    if (invalid || !std::isfinite(sse)) throw std::runtime_error("Nonfinite distance or objective (rescale input)");
    stats.sse = sse;
    const double merge_start = phases ? wall_time() : 0;
    if (phases) phases->accumulate += merge_start - start;
    if (local) {
        // 隐式线程屏障后按固定线程编号合并；不同线程数仍可能改变浮点舍入顺序。
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
        // 先比较剩余额度再相加，同时检查负数、总数越界和整数溢出。
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
            // 空簇保留旧质心，避免除零，并保持所有版本的更新规则一致。
            const double next = stats.counts[k] ? stats.sums[j] / static_cast<double>(stats.counts[k]) : old;
            // hypot 逐维累积范数，减少直接平方求和时的中间溢出风险。
            movement = std::hypot(movement, next - old);
            norm = std::hypot(norm, old);
            centers[j] = next;
        }
        max_move = std::max(max_move, movement); max_norm = std::max(max_norm, norm);
    }
    // 相对位移以旧质心的最大范数为尺度，下限 1 防止零质心导致除零。
    const double delta = max_move / std::max(1.0, max_norm);
    if (!std::isfinite(delta)) throw std::runtime_error("Nonfinite centroid shift");
    return delta;
}
}
