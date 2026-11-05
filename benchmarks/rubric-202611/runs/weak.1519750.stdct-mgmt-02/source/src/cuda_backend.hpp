#pragma once
#include "core.hpp"
#include <memory>

namespace km {
// Optional V4 backend. The CPU-only targets never include CUDA headers or link cudart.
class CudaBackend {
    struct Impl;
    std::unique_ptr<Impl> impl;
public:
    CudaBackend(const std::vector<double>& data, const Config& c);
    ~CudaBackend();
    void accumulate(const std::vector<double>& centers, Stats& stats, bool objective,
                    std::vector<int>* labels, Phases* phases);
    void reset_profile();
    std::string metadata() const;
};
}
