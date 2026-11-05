#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace km {
// 全局样本数和簇计数统一使用 64 位整数，与 MPI_INT64_T 对应。
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
// 当前进程负责的全局样本区间为 [first, first + size)，允许 size=0。
struct Partition { Count first, size; };
struct Stats {
    // 按簇存储充分统计量：sums[k*D+j] 为坐标和，counts[k] 为成员数。
    // 归约这些统计量后再求均值，才能正确处理各进程簇大小不一致的情况。
    std::vector<double> sums;
    std::vector<Count> counts;
    double sse = 0;
    Stats(int k, int d);
    void clear();
};
struct Workspace {
    // 仅 V3 分配；每个线程通过 stride 定位独立缓冲，避免样本循环内同步。
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
// 每次调用清零并重新计算本地统计；objective/labels/phases 按需启用，
// 普通迭代无需保存标签或累加 SSE，减少性能测量中的额外工作。
void accumulate(const std::vector<double>& data, const std::vector<double>& centers,
                const Config& c, Workspace& work, Stats& stats, bool objective,
                std::vector<int>* labels, Phases* phases);
// stats 必须覆盖全局 N 个样本；原地更新质心并返回相对最大质心位移。
double update(std::vector<double>& centers, const Stats& stats, const Config& c);
void check_stats(const Stats& stats, Count n, bool objective);
}
