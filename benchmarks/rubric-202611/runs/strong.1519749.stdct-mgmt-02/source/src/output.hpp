#pragma once
#include "core.hpp"
#include <cstdlib>
#include <iomanip>
#include <ostream>
#include <sstream>

namespace km {
inline std::string quote(const std::string& value) {
    // MPI 版本等元数据可能包含换行或控制字符，必须转义后才能写成合法 JSON。
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
    // 同一轮记录中：目标函数/计数对应旧质心，centers 对应更新后的质心。
    double sse_before, shift;
    std::vector<Count> counts;
    std::vector<double> centers;
};
inline std::string env(const char* name) { const char* p = std::getenv(name); return p ? p : "unset"; }
}
