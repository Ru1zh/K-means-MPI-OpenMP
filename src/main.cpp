#include "core.hpp"
#include "runtime.hpp"
#include "output.hpp"
#include <cmath>
#include <iostream>
#include <sstream>

namespace {
void write_phases(std::ostream& out, const km::Phases& phases) {
    out << "{\"accumulate\":" << phases.accumulate << ",\"thread_merge\":" << phases.merge
        << ",\"mpi_reduce\":" << phases.reduce << ",\"centroid_update\":" << phases.update
        << ",\"control_bcast\":" << phases.control << '}';
}
void help() {
    std::cout << "Lloyd K-means: C++17 / MPI+OpenMP\n"
        "--n N --d D --k K --seed S [--skew]\n"
        "--input FILE             whitespace file: N D then N*D finite doubles\n"
        "--init-indices 0,2,...    K unique global sample IDs (default seeded sampling)\n"
        "--variant v1|v2|v3       MPI, atomic, thread-private (serial binary: v0)\n"
        "--comm allreduce|reduce-bcast --threads T\n"
        "--mode fixed|converge --iterations I --tol EPS --warmup I\n"
        "--dump                   small-data labels, final and initial centers\n"
        "--trace                  per-iteration SSE before update, counts, new centers\n"
        "--profile                independent phase-timing run\n"
        "Defaults: N=10000 D=8 K=16 seed=42 T=1; fixed=50 / converge=300, tol=1e-6\n"
        "JSON result goes to stdout. Failures go to stderr and terminate all ranks.\n";
}
}
int main(int argc, char** argv) {
    km::Runtime rt(argc, argv);
    try {
        const double total_start = rt.time();
#ifdef KM_MPI
        constexpr bool parallel = true;
#else
        constexpr bool parallel = false;
#endif
        auto c = km::parse(argc, argv, parallel);
        if (c.help) { if (!rt.rank) help(); return 0; }
        std::vector<double> full;
        const double data_start = rt.time();
        if (!c.input.empty()) {
            // The file header determines the actual N and D; synchronize sizes first, then let all processes validate and partition by the same rule.
            if (!rt.rank) full = km::read_data(c.input, c.n, c.d);
            rt.dimensions(c);
        }
        km::validate(c);
        const int actual_threads = rt.configure_threads(c.threads);
        const auto part = km::partition(c.n, rt.rank, rt.size);
        auto data = c.input.empty() ? km::generate(c, part) : rt.scatter(full, c);
        const double data_seconds = rt.time() - data_start;
        const double init_start = rt.time();
        const auto ids = km::initial_indices(c);
        std::vector<double> centers(km::elements(c.k, c.d));
        if (!rt.rank) centers = km::initial_centers(c, ids, full);
        // All processes start from the same initial centroids; root no longer needs to keep the full input copy.
        rt.broadcast(centers);
        std::vector<double>().swap(full);
        const auto initial = centers;
        const auto data_hash = rt.xor_hash(km::fingerprint(data, part.first, c.d));
        const double init_seconds = rt.time() - init_start;
        km::Workspace workspace(c);
        km::Stats local(c.k, c.d), global(c.k, c.d);
        km::Phases phases;
        std::vector<km::Trace> trace;
        if (c.trace) trace.reserve(c.iterations);
        const bool all = c.comm == "allreduce";
        // One Lloyd iteration: local assignment/accumulation -> global statistics -> centroid update -> broadcast if needed.
        // All processes must execute collective calls in the same order, including processes with no local samples.
        auto step = [&](bool diagnostic, km::Phases* prof) {
            km::accumulate(data, centers, c, workspace, local, diagnostic, nullptr, prof);
            double start = prof ? rt.time() : 0;
            rt.reduce(local, global, all);
            if (prof) phases.reduce += rt.time() - start;
            // Per-iteration SSE needs an extra reduction and is enabled only for trace diagnostics.
            if (diagnostic) global.sse = rt.sum(local.sse);
            start = prof ? rt.time() : 0;
            double shift = 0;
            // After Allreduce every process holds the statistics; after Reduce only root's receive buffer is valid.
            if (all || !rt.rank) shift = km::update(centers, global, c);
            if (prof) phases.update += rt.time() - start;
            start = prof ? rt.time() : 0;
            if (!all) rt.broadcast(centers);
            if (prof) phases.control += rt.time() - start;
            if (diagnostic && !rt.rank) {
                km::check_stats(global, c.n, true);
                // sse/counts describe the assignment to the pre-update centroids; centers are the centroids updated in this round.
                trace.push_back({global.sse, shift, global.counts, centers});
            }
            return shift;
        };
        const double warmup_start = rt.time();
        for (int i = 0; i < c.warmup; ++i) step(false, nullptr);
        // Warmup only starts threads and warms caches; measurement must restore the original state to keep the same workload.
        centers = initial; local.clear(); global.clear();
        const double warmup_seconds = rt.time() - warmup_start;
        // Synchronize only before the kernel starts, not with an extra barrier per iteration that would disturb real communication.
        rt.barrier();
        const double kernel_start = rt.time();
        std::string reason = c.mode == "fixed" ? "fixed_iterations" : "max_iterations";
        int iterations = 0;
        for (int i = 0; i < c.iterations; ++i) {
            const double shift = step(c.trace, c.profile ? &phases : nullptr);
            ++iterations;
            if (c.mode == "converge") {
                const double start = c.profile ? rt.time() : 0;
                // Let root make the decision so processes cannot diverge into different collective calls due to local checks.
                int stop = rt.rank == 0 && shift <= c.tol;
                rt.broadcast(stop);
                if (c.profile) phases.control += rt.time() - start;
                if (stop) { reason = "converged"; break; }
            }
        }
        const double kernel_seconds = rt.time() - kernel_start;
        const double eval_start = rt.time();
        std::vector<int> labels;
        // The last accumulation corresponds to the pre-update centroids; reassignment is required to obtain final labels, counts and SSE.
        km::accumulate(data, centers, c, workspace, local, true, c.dump ? &labels : nullptr, nullptr);
        // Final evaluation is identical for both communication strategies and outside kernel timing.
        rt.reduce(local, global, true);
        global.sse = rt.sum(local.sse);
        km::check_stats(global, c.n, true);
        if (c.dump) labels = rt.gather_labels(labels, c.n);
        const double evaluation_seconds = rt.time() - eval_start;
        const double total_seconds = rt.time() - total_start;
        // Reduce local elapsed-time differences only, avoiding assumptions about synchronized node clocks; the slowest process determines parallel time.
        const double data_max = rt.maximum(data_seconds), init_max = rt.maximum(init_seconds);
        const double warmup_max = rt.maximum(warmup_seconds), kernel_max = rt.maximum(kernel_seconds);
        const double eval_max = rt.maximum(evaluation_seconds), total_max = rt.maximum(total_seconds);
        std::vector<double> profile_ranks;
        if (c.profile) {
            // Save the local originals first; the diagnostic gather is excluded from kernel and ordinary total time.
            profile_ranks = rt.gather_profile({kernel_seconds, phases.accumulate, phases.merge,
                                              phases.reduce, phases.update, phases.control});
            // Phase maxima may come from different processes and cannot be summed to reconstruct kernel time.
            phases.accumulate = rt.maximum(phases.accumulate); phases.merge = rt.maximum(phases.merge);
            phases.reduce = rt.maximum(phases.reduce); phases.update = rt.maximum(phases.update);
            phases.control = rt.maximum(phases.control);
        }
        if (!rt.rank) {
            // Only root prints the complete JSON so multi-process stdout cannot interleave and corrupt the experiment record.
            std::ostringstream hash; hash << std::hex << data_hash;
            auto& out = std::cout;
            out << std::setprecision(17) << '{'
                << "\"n\":" << c.n << ",\"d\":" << c.d << ",\"k\":" << c.k
                << ",\"p\":" << rt.size << ",\"t\":" << actual_threads << ",\"nodes\":" << rt.nodes
                << ",\"variant\":" << km::quote(c.variant) << ",\"communication\":" << km::quote(c.comm)
                << ",\"mode\":" << km::quote(c.mode) << ",\"seed\":" << c.seed
                << ",\"skew\":" << (c.skew ? "true" : "false") << ",\"input\":" << km::quote(c.input)
                << ",\"generator\":" << km::quote(c.input.empty() ? "hash-box-muller-v1;groups=16;sigma=1" : "text-v1")
                << ",\"data_fingerprint\":" << km::quote(hash.str())
                << ",\"iterations\":" << iterations << ",\"requested_iterations\":" << c.iterations
                << ",\"tolerance\":" << c.tol << ",\"warmup\":" << c.warmup
                << ",\"stop_reason\":" << km::quote(reason) << ",\"sse\":" << global.sse
                << ",\"data_seconds\":" << data_max << ",\"initialization_seconds\":" << init_max
                << ",\"warmup_seconds\":" << warmup_max << ",\"kernel_seconds\":" << kernel_max
                << ",\"evaluation_seconds\":" << eval_max << ",\"total_seconds\":" << total_max
                << ",\"diagnostic\":" << ((c.trace || c.profile) ? "true" : "false")
                << ",\"compiler\":" << km::quote(__VERSION__) << ",\"mpi_version\":" << km::quote(rt.library)
                << ",\"omp_places\":" << km::quote(km::env("OMP_PLACES"))
                << ",\"omp_proc_bind\":" << km::quote(km::env("OMP_PROC_BIND"))
                << ",\"binding_note\":" << km::quote(km::env("KMEANS_BINDING_NOTE"))
                << ",\"init_indices\":"; km::array(out, ids);
            out << ",\"counts\":"; km::array(out, global.counts);
            if (c.dump) {
                out << ",\"initial_centers\":"; km::array(out, initial);
                out << ",\"centers\":"; km::array(out, centers);
                out << ",\"labels\":"; km::array(out, labels);
            }
            if (c.trace) {
                out << ",\"trace\":[";
                for (std::size_t i = 0; i < trace.size(); ++i) {
                    if (i) out << ',';
                    out << "{\"iteration\":" << i + 1 << ",\"sse_before\":" << trace[i].sse_before
                        << ",\"shift\":" << trace[i].shift << ",\"counts\":";
                    km::array(out, trace[i].counts); out << ",\"centers\":"; km::array(out, trace[i].centers);
                    out << '}';
                }
                out << ']';
            }
            if (c.profile) {
                out << ",\"phase_seconds\":"; write_phases(out, phases);
                out << ",\"profile_ranks\":[";
                int critical_rank = 0;
                for (int rank = 0; rank < rt.size; ++rank) {
                    const auto offset = static_cast<std::size_t>(rank) * 6;
                    // Replace only on a strictly greater value, so ties in timing keep the lowest rank.
                    if (profile_ranks[offset] > profile_ranks[static_cast<std::size_t>(critical_rank) * 6])
                        critical_rank = rank;
                    if (rank) out << ',';
                    out << "{\"rank\":" << rank << ",\"kernel_seconds\":" << profile_ranks[offset]
                        << ",\"phase_seconds\":";
                    write_phases(out, {profile_ranks[offset + 1], profile_ranks[offset + 2],
                                       profile_ranks[offset + 3], profile_ranks[offset + 4],
                                       profile_ranks[offset + 5]});
                    out << '}';
                }
                out << "],\"profile_critical_rank\":" << critical_rank;
            }
            out << "}\n";
        }
        return 0;
    } catch (const std::exception& e) { rt.fail(e.what()); }
}
