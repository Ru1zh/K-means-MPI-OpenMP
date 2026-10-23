#pragma once
#include "core.hpp"
#include <algorithm>
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
// 封装通信与生命周期；串行构建使用本地操作，和并行构建共享同一算法流程。
// MPI 调用均由初始化 MPI 的主线程执行，不能从 OpenMP 工作线程调用这些方法。
class Runtime {
public:
    int rank = 0, size = 1, nodes = 1;
    std::string library = "none";
    Runtime(int& argc, char**& argv) {
#ifdef KM_MPI
        int provided = 0;
        // FUNNELED 允许 OpenMP 计算线程存在，但 MPI 调用必须由初始化线程执行。
        MPI_Init_thread(&argc, &argv, MPI_THREAD_FUNNELED, &provided);
        MPI_Comm_rank(MPI_COMM_WORLD, &rank); MPI_Comm_size(MPI_COMM_WORLD, &size);
        if (provided < MPI_THREAD_FUNNELED) fail("MPI_THREAD_FUNNELED unavailable");
        char version[MPI_MAX_LIBRARY_VERSION_STRING]; int length = 0;
        MPI_Get_library_version(version, &length); library.assign(version, length);
        // Some implementations count the C terminator in the returned length.
        library.erase(std::find(library.begin(), library.end(), '\0'), library.end());
        MPI_Comm shared;
        // 每个共享内存通信域选一个代表，汇总代表数量作为实际节点数。
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
        // 单个进程退出会让其他进程卡在集合通信中，因此错误时终止整个通信域。
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
    // all=true 时所有进程收到结果，否则仅 root 收到；SSE 由调用方按需单独归约。
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
        // Scatterv 的长度和偏移按 double 元素数计算，而不是按样本数或字节数。
        // read_data 已限制 N*D<=INT_MAX，因此这里转换为 int 是安全的。
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
        // 仅 --dump 的小数据路径收集标签，正常大规模测量只归约统计量。
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
    int configure_threads(int requested) const {
#ifdef KM_MPI
        // 关闭动态缩小线程组；若资源限制使任一进程未达到请求线程数，统一报错。
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
