#include "cuda_backend.hpp"
#include "output.hpp"
#include <cuda_runtime.h>
#include <math_constants.h>
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace km {
namespace {
void checked(cudaError_t code) {
    if (code != cudaSuccess) throw std::runtime_error(std::string("CUDA: ") + cudaGetErrorString(code));
}
template<class T> struct DeviceArray {
    T* data = nullptr;
    explicit DeviceArray(std::size_t n) {
        if (n) checked(cudaMalloc(reinterpret_cast<void**>(&data), n * sizeof(T)));
    }
    ~DeviceArray() { if (data) cudaFree(data); }
    DeviceArray(const DeviceArray&) = delete;
    DeviceArray& operator=(const DeviceArray&) = delete;
};
// Each block owns a statistics tile. Atomics are confined to that tile; a second
// kernel reduces the tiles. No N*K distance matrix or per-point D-vector copy.
__global__ void assign(const double* points, const double* centers, Count n, int d, int k,
                       double* sums, unsigned long long* counts, double* objectives,
                       int* labels, bool objective, int* invalid) {
    double* tile = sums + static_cast<std::size_t>(blockIdx.x) * k * d;
    auto* count = counts + static_cast<std::size_t>(blockIdx.x) * k;
    for (Count i = static_cast<Count>(blockIdx.x) * blockDim.x + threadIdx.x;
         i < n; i += static_cast<Count>(gridDim.x) * blockDim.x) {
        const double* x = points + static_cast<std::size_t>(i) * d;
        double best = CUDART_INF;
        int label = 0;
        for (int group = 0; group < k; ++group) {
            double distance = 0;
            for (int j = 0; j < d; ++j) {
                const double delta = x[j] - centers[static_cast<std::size_t>(group) * d + j];
                distance += delta * delta;
            }
            if (distance < best) { best = distance; label = group; } // smallest ID wins ties
        }
        if (!isfinite(best)) { atomicExch(invalid, 1); continue; }
        if (labels) labels[i] = label;
        atomicAdd(count + label, 1ULL);
        for (int j = 0; j < d; ++j)
            atomicAdd(tile + static_cast<std::size_t>(label) * d + j, x[j]);
        if (objective) atomicAdd(objectives + blockIdx.x, best);
    }
}
__global__ void merge_tiles(const double* tiles, const unsigned long long* counts,
                            const double* objectives, double* sums, Count* total,
                            double* sse, int blocks, int k, int d) {
    const std::size_t len = static_cast<std::size_t>(k) * d;
    const std::size_t id = static_cast<std::size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (id < len) {
        double sum = 0;
        for (int block = 0; block < blocks; ++block) sum += tiles[block * len + id];
        sums[id] = sum;
    }
    if (id < static_cast<std::size_t>(k)) {
        unsigned long long count = 0;
        for (int block = 0; block < blocks; ++block) count += counts[static_cast<std::size_t>(block) * k + id];
        total[id] = static_cast<Count>(count);
    }
    if (!id) {
        double sum = 0;
        for (int block = 0; block < blocks; ++block) sum += objectives[block];
        *sse = sum;
    }
}
struct Events {
    cudaEvent_t begin{}, end{};
    Events() { checked(cudaEventCreate(&begin)); checked(cudaEventCreate(&end)); }
    ~Events() { cudaEventDestroy(begin); cudaEventDestroy(end); }
    template<class F> double measure(bool enabled, F operation) {
        if (enabled) checked(cudaEventRecord(begin));
        operation();
        if (!enabled) return 0;
        checked(cudaEventRecord(end)); checked(cudaEventSynchronize(end));
        float ms = 0; checked(cudaEventElapsedTime(&ms, begin, end));
        return static_cast<double>(ms) * 0.001;
    }
};
}
struct CudaBackend::Impl {
    Config c;
    Count n;
    int blocks;
    DeviceArray<double> points, centers, tiles, objectives, sums, sse;
    DeviceArray<unsigned long long> counts;
    DeviceArray<Count> totals;
    DeviceArray<int> labels, invalid;
    Events events;
    cudaDeviceProp device{};
    int driver = 0, runtime = 0;
    double upload = 0, h2d = 0, assignment = 0, merge = 0, d2h = 0;
    std::uint64_t launches = 0;
    static int configure() {
        int count = 0; checked(cudaGetDeviceCount(&count));
        if (count < 1) throw std::runtime_error("CUDA: no visible GPU; CPU fallback is forbidden");
        checked(cudaSetDevice(0));
        cudaDeviceProp prop{}; checked(cudaGetDeviceProperties(&prop, 0));
        if (prop.major < 6) throw std::runtime_error("V4 requires compute capability >= 6.0 for FP64 atomicAdd");
        return std::min(256, prop.multiProcessorCount * 4);
    }
    Impl(const std::vector<double>& data, const Config& config)
        : c(config), n(static_cast<Count>(data.size() / c.d)), blocks(configure()),
          points(data.size()), centers(elements(c.k, c.d)),
          tiles(elements(c.k, c.d) * blocks), objectives(blocks),
          sums(elements(c.k, c.d)), sse(1), counts(static_cast<std::size_t>(c.k) * blocks),
          totals(c.k), labels(c.dump ? static_cast<std::size_t>(n) : 0), invalid(1) {
        checked(cudaGetDeviceProperties(&device, 0));
        checked(cudaDriverGetVersion(&driver)); checked(cudaRuntimeGetVersion(&runtime));
        const double start = wall_time();
        if (!data.empty()) checked(cudaMemcpy(points.data, data.data(), data.size() * sizeof(double), cudaMemcpyHostToDevice));
        checked(cudaDeviceSynchronize());
        upload = wall_time() - start;
    }
};
CudaBackend::CudaBackend(const std::vector<double>& data, const Config& c) : impl(new Impl(data, c)) {}
CudaBackend::~CudaBackend() = default;
void CudaBackend::reset_profile() {
    impl->h2d = impl->assignment = impl->merge = impl->d2h = 0;
    impl->launches = 0;
}
void CudaBackend::accumulate(const std::vector<double>& centers, Stats& stats, bool objective,
                            std::vector<int>* labels, Phases* phases) {
    auto& b = *impl;
    const bool profile = phases != nullptr;
    const double start = profile ? wall_time() : 0;
    b.h2d += b.events.measure(profile, [&] {
        checked(cudaMemcpy(b.centers.data, centers.data(), centers.size() * sizeof(double), cudaMemcpyHostToDevice));
    });
    checked(cudaMemset(b.tiles.data, 0, elements(b.c.k, b.c.d) * b.blocks * sizeof(double)));
    checked(cudaMemset(b.counts.data, 0, static_cast<std::size_t>(b.c.k) * b.blocks * sizeof(unsigned long long)));
    checked(cudaMemset(b.objectives.data, 0, b.blocks * sizeof(double)));
    checked(cudaMemset(b.invalid.data, 0, sizeof(int)));
    b.assignment += b.events.measure(profile, [&] {
        assign<<<b.blocks, 256>>>(b.points.data, b.centers.data, b.n, b.c.d, b.c.k,
                                 b.tiles.data, b.counts.data, b.objectives.data,
                                 labels ? b.labels.data : nullptr, objective, b.invalid.data);
        checked(cudaGetLastError()); ++b.launches;
    });
    // Synchronous boundaries are required even in ordinary runs: the CPU must see
    // completed statistics before the existing host MPI reduction/centroid update.
    checked(cudaDeviceSynchronize());
    const double middle = profile ? wall_time() : 0;
    if (profile) phases->accumulate += middle - start;
    b.merge += b.events.measure(profile, [&] {
        merge_tiles<<<static_cast<unsigned>((centers.size() + 255) / 256), 256>>>(
            b.tiles.data, b.counts.data, b.objectives.data, b.sums.data, b.totals.data,
            b.sse.data, b.blocks, b.c.k, b.c.d);
        checked(cudaGetLastError()); ++b.launches;
    });
    checked(cudaDeviceSynchronize());
    if (profile) phases->merge += wall_time() - middle;
    const double copy_start = profile ? wall_time() : 0;
    int invalid = 0;
    b.d2h += b.events.measure(profile, [&] {
        checked(cudaMemcpy(stats.sums.data(), b.sums.data, stats.sums.size() * sizeof(double), cudaMemcpyDeviceToHost));
        checked(cudaMemcpy(stats.counts.data(), b.totals.data, stats.counts.size() * sizeof(Count), cudaMemcpyDeviceToHost));
        checked(cudaMemcpy(&stats.sse, b.sse.data, sizeof(double), cudaMemcpyDeviceToHost));
        checked(cudaMemcpy(&invalid, b.invalid.data, sizeof(int), cudaMemcpyDeviceToHost));
        if (labels) {
            labels->resize(static_cast<std::size_t>(b.n));
            if (b.n) checked(cudaMemcpy(labels->data(), b.labels.data, labels->size() * sizeof(int), cudaMemcpyDeviceToHost));
        }
    });
    // CPU phase accounting remains disjoint; transfers are in local accumulation.
    if (profile) phases->accumulate += wall_time() - copy_start;
    if (invalid || !std::isfinite(stats.sse)) throw std::runtime_error("CUDA: nonfinite distance/objective");
}
std::string CudaBackend::metadata() const {
    const auto& b = *impl;
    std::ostringstream uuid;
    uuid << std::hex << std::setfill('0');
    for (unsigned char byte : b.device.uuid.bytes) uuid << std::setw(2) << static_cast<unsigned>(byte);
    std::ostringstream out;
    out << std::setprecision(17) << "{\"name\":" << quote(b.device.name)
        << ",\"uuid\":" << quote(uuid.str()) << ",\"driver_version\":" << b.driver
        << ",\"runtime_version\":" << b.runtime << ",\"compute_major\":" << b.device.major
        << ",\"compute_minor\":" << b.device.minor << ",\"global_memory_bytes\":" << b.device.totalGlobalMem
        << ",\"kernel_launches\":" << b.launches << ",\"initial_upload_seconds\":" << b.upload;
    if (b.c.profile) out << ",\"phase_seconds\":{\"h2d\":" << b.h2d << ",\"assignment\":" << b.assignment
        << ",\"merge\":" << b.merge << ",\"d2h\":" << b.d2h << '}';
    return out.str() + '}';
}
}
