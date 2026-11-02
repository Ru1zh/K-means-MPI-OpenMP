#pragma once
#include "core.hpp"
#include <cstdlib>
#include <iomanip>
#include <ostream>
#include <sstream>

namespace km {
inline std::string quote(const std::string& value) {
    // Metadata such as the MPI version may contain newlines or control characters and must be escaped to produce valid JSON.
    std::ostringstream out;
    out << '"';
    for (unsigned char ch : value) {
        if (ch == '"' || ch == '\\') out << '\\' << ch;
        else if (ch < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(ch);
        else out << ch;
    }
    out << '"'; return out.str();
}
template<class T> void array(std::ostream& out, const std::vector<T>& values) {
    out << '[';
    for (std::size_t i = 0; i < values.size(); ++i) { if (i) out << ','; out << values[i]; }
    out << ']';
}
struct Trace {
    // In a round record, the objective/counts refer to the old centroids and centers to the updated centroids.
    double sse_before, shift;
    std::vector<Count> counts;
    std::vector<double> centers;
};
inline std::string env(const char* name) { const char* p = std::getenv(name); return p ? p : "unset"; }
}
