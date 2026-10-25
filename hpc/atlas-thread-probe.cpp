// Separate Linux/OpenMP placement probe; not part of K-means timing.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <omp.h>
#include <cstdlib>
#include <iostream>
#include <vector>
#ifdef __linux__
#include <sched.h>
#endif

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    const int requested = std::atoi(argv[1]);
    if (requested < 1 || requested > 1024) return 2;
#ifndef __linux__
    std::cerr << "CPU affinity probe requires Linux\n";
    return 1;
#else
    omp_set_dynamic(0);
    std::vector<std::vector<int>> masks(requested);
    std::vector<int> current(requested, -1);
    int observed = 0, failed = 0;
    #pragma omp parallel num_threads(requested) reduction(|:failed)
    {
        const int tid = omp_get_thread_num();
        #pragma omp single
        observed = omp_get_num_threads();
        cpu_set_t mask;
        CPU_ZERO(&mask);
        if (sched_getaffinity(0, sizeof(mask), &mask)) failed = 1;
        else for (int cpu = 0; cpu < CPU_SETSIZE; ++cpu)
            if (CPU_ISSET(cpu, &mask)) masks[tid].push_back(cpu);
        current[tid] = sched_getcpu();
    }
    if (observed != requested || failed) return 1;
    std::cout << "{\"openmp\":" << _OPENMP << ",\"threads\":[";
    for (int tid = 0; tid < observed; ++tid) {
        if (tid) std::cout << ',';
        std::cout << "{\"tid\":" << tid << ",\"current_cpu\":" << current[tid] << ",\"cpus\":[";
        for (std::size_t j = 0; j < masks[tid].size(); ++j) {
            if (j) std::cout << ',';
            std::cout << masks[tid][j];
        }
        std::cout << "]}";
    }
    std::cout << "]}\n";
    return 0;
#endif
}
