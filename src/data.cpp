#include "core.hpp"
#include <algorithm>
#include <charconv>
#include <climits>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>
#include <unordered_set>

namespace km {
namespace {
template<class T> T integer(const std::string& s) {
    // Require the whole string to be an integer; reject overflow and partially parsed inputs such as "9x".
    T value{};
    const auto r = std::from_chars(s.data(), s.data() + s.size(), value);
    if (r.ec != std::errc{} || r.ptr != s.data() + s.size())
        throw std::runtime_error("Invalid integer: " + s);
    return value;
}
std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
double uniform(std::uint64_t x) {
    // Strictly inside (0,1); avoids log(0) in Box-Muller.
    return (static_cast<double>(mix(x) >> 12) + 0.5) * 0x1p-52;
}
void sample(const Config& c, Count id, double* out) {
    // Random values depend only on the seed, global sample index and dimension; changing the MPI partition does not change the data.
    const auto key = mix(c.seed ^ mix(static_cast<std::uint64_t>(id)));
    const double choice = uniform(key);
    // The generator always uses 16 clusters, independent of K; skew mode assigns 90% probability to cluster 0.
    const int group = c.skew ? (choice < 0.9 ? 0 : 1 + std::min(14, int((choice - 0.9) * 150)))
                             : std::min(15, int(choice * 16));
    for (int j = 0; j < c.d; ++j) {
        const auto axis = mix(key ^ mix(static_cast<std::uint64_t>(j) + 1));
        const double center = 20 * (uniform(c.seed ^ mix(0x12340000ULL + group * 131ULL + j)) - 0.5);
        // Box-Muller turns two uniform random values into standard normal noise and adds the cluster's fixed center.
        out[j] = center + std::sqrt(-2 * std::log(uniform(axis))) *
                 std::cos(6.2831853071795864769 * uniform(axis ^ 0xabcd0123456789ULL));
    }
}
}
Config parse(int argc, char** argv, bool parallel) {
    Config c;
    if (parallel) c.variant = "v3";
    bool set_iterations = false;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (key == "--help") { c.help = true; continue; }
        if (key == "--skew") { c.skew = true; continue; }
        if (key == "--dump") { c.dump = true; continue; }
        if (key == "--trace") { c.trace = true; continue; }
        if (key == "--profile") { c.profile = true; continue; }
        if (++i >= argc) throw std::runtime_error("Missing value for " + key);
        const std::string value = argv[i];
        if (key == "--n") c.n = integer<Count>(value);
        else if (key == "--d") c.d = integer<int>(value);
        else if (key == "--k") c.k = integer<int>(value);
        else if (key == "--seed") c.seed = integer<std::uint64_t>(value);
        else if (key == "--threads") c.threads = integer<int>(value);
        else if (key == "--warmup") c.warmup = integer<int>(value);
        else if (key == "--iterations") { c.iterations = integer<int>(value); set_iterations = true; }
        else if (key == "--variant") c.variant = value;
        else if (key == "--comm") c.comm = value;
        else if (key == "--mode") c.mode = value;
        else if (key == "--input") c.input = value;
        else if (key == "--init-indices") c.init_spec = value;
        else if (key == "--tol") {
            std::size_t pos = 0;
            c.tol = std::stod(value, &pos);
            if (pos != value.size()) throw std::runtime_error("Invalid tolerance");
        } else throw std::runtime_error("Unknown option: " + key);
    }
    if (!set_iterations && c.mode == "converge") c.iterations = 300;
    if (!parallel && (c.variant != "v0" || c.threads != 1))
        throw std::runtime_error("Serial executable requires v0 and one thread");
    if (parallel && c.variant == "v0") throw std::runtime_error("Use kmeans_serial for v0");
    return c;
}
std::size_t elements(Count n, int d) {
    // Check the byte-count range with division first, then multiply, to avoid integer overflow before allocation.
    if (n < 0 || d <= 0 || static_cast<std::uint64_t>(n) >
        std::numeric_limits<std::size_t>::max() / sizeof(double) / static_cast<unsigned>(d))
        throw std::runtime_error("Array size overflow");
    return static_cast<std::size_t>(n) * static_cast<std::size_t>(d);
}
void validate(const Config& c) {
    if (c.n <= 0 || c.d <= 0 || c.k < 1 || c.k > c.n) throw std::runtime_error("Require N,D>0 and 1<=K<=N");
    if (c.threads < 1 || c.iterations < 1 || c.warmup < 0 || !std::isfinite(c.tol) || c.tol < 0)
        throw std::runtime_error("Invalid threads, iterations, warmup or tolerance");
    if (c.variant != "v0" && c.variant != "v1" && c.variant != "v2" && c.variant != "v3")
        throw std::runtime_error("variant must be v0, v1, v2 or v3");
    if (c.variant == "v1" && c.threads != 1) throw std::runtime_error("v1 requires one thread");
    if (c.comm != "allreduce" && c.comm != "reduce-bcast") throw std::runtime_error("Invalid communication strategy");
    if (c.mode != "fixed" && c.mode != "converge") throw std::runtime_error("Invalid mode");
    elements(c.n, c.d);
    if (elements(c.k, c.d) > INT_MAX) throw std::runtime_error("K*D exceeds MPI int count limit");
    if ((c.dump || c.trace) && (c.n > 100000 || elements(c.k, c.d) > 100000))
        throw std::runtime_error("dump/trace restricted to N and K*D <= 100000");
}
Partition partition(Count n, int rank, int size) {
    // Give the remainder to the first rem processes so sample counts differ by at most 1; when P>N later processes own empty ranges.
    const Count base = n / size, rem = n % size;
    return {rank * base + std::min<Count>(rank, rem), base + (rank < rem)};
}
std::vector<double> read_data(const std::string& path, Count& n, int& d) {
    std::ifstream f(path);
    std::string ns, ds;
    if (!(f >> ns >> ds)) throw std::runtime_error("Cannot read N D header: " + path);
    n = integer<Count>(ns); d = integer<int>(ds);
    if (n <= 0 || d <= 0) throw std::runtime_error("Invalid file dimensions");
    const auto len = elements(n, d);
    // Text input uses traditional Scatterv whose count/displacement are int; large data uses direct generation.
    if (len > INT_MAX) throw std::runtime_error("Text input limited to INT_MAX elements; use generated data for larger runs");
    std::vector<double> data(len);
    for (double& value : data) {
        if (!(f >> value) || !std::isfinite(value)) throw std::runtime_error("Missing or nonfinite coordinate");
    }
    std::string extra;
    if (f >> extra) throw std::runtime_error("Extra data after N*D coordinates");
    return data;
}
std::vector<double> generate(const Config& c, Partition p) {
    std::vector<double> data(elements(p.size, c.d));
    for (Count i = 0; i < p.size; ++i) sample(c, p.first + i, data.data() + elements(i, c.d));
    return data;
}
std::vector<Count> initial_indices(const Config& c) {
    std::vector<Count> ids;
    std::unordered_set<Count> selected;
    if (!c.init_spec.empty()) {
        std::istringstream stream(c.init_spec);
        std::string token;
        while (std::getline(stream, token, ',')) ids.push_back(integer<Count>(token));
        if (c.init_spec.back() == ',') throw std::runtime_error("Empty initial index");
    } else {
        // Floyd sampling without replacement is O(K) in time and space and needs no repeated attempts even when K=N.
        std::mt19937_64 rng(c.seed);
        for (Count j = c.n - c.k; j < c.n; ++j) {
            const auto bound = static_cast<std::uint64_t>(j) + 1;
            // Reject low random values that cannot be split evenly into bound parts, removing modulo sampling bias.
            const auto threshold = -bound % bound;
            std::uint64_t value;
            do { value = rng(); } while (value < threshold);
            Count id = static_cast<Count>(value % bound);
            // On collision choose j; earlier rounds have not selected j yet, so uniqueness is preserved.
            if (selected.count(id)) id = j;
            selected.insert(id); ids.push_back(id);
        }
        selected.clear();
    }
    if (ids.size() != static_cast<std::size_t>(c.k)) throw std::runtime_error("Need K initial indices");
    for (auto id : ids)
        if (id < 0 || id >= c.n || !selected.insert(id).second) throw std::runtime_error("Initial indices must be distinct and in range");
    return ids;
}
std::vector<double> initial_centers(const Config& c, const std::vector<Count>& ids,
                                    const std::vector<double>& full) {
    std::vector<double> centers(elements(c.k, c.d));
    for (int k = 0; k < c.k; ++k) {
        double* dest = centers.data() + elements(k, c.d);
        if (c.input.empty()) sample(c, ids[k], dest);
        else std::copy_n(full.data() + elements(ids[k], c.d), c.d, dest);
    }
    return centers;
}
std::uint64_t fingerprint(const std::vector<double>& data, Count first, int d) {
    // Mix coordinate bit patterns with the global position, then XOR: after cross-process reduction the result is independent of partitioning.
    // This is a data-consistency fingerprint, not a cryptographic hash.
    std::uint64_t result = 0;
    const auto start = static_cast<std::uint64_t>(first) * static_cast<unsigned>(d);
    for (std::size_t i = 0; i < data.size(); ++i) {
        std::uint64_t bits;
        std::memcpy(&bits, &data[i], sizeof bits);
        result ^= mix(bits ^ mix(start + i));
    }
    return result;
}
}
