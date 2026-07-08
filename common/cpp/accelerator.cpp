// Optional shared compute-heavy helper, invoked identically (via
// subprocess) from both Traditional/services and FaaS/functions so
// it doesn't skew the Part 4 architecture comparison -- it's the
// same binary either way. Intended home for whatever Part 3 feature
// needs real compute (e.g. predictive scheduling / historical-load
// scoring), echoing the HW1 optimization work.
//
// Placeholder body: reads an integer N from argv[1], does an N-sized
// piece of busywork, prints a JSON result to stdout. Replace the body
// once the Part 3 feature is chosen; keep the "read args -> print
// JSON to stdout" contract so both callers keep working unchanged.
//
// Build: ./build.sh  ->  build/accelerator

#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    long n = argc > 1 ? std::atol(argv[1]) : 1000;

    long long acc = 0;
    for (long i = 0; i < n; ++i) {
        acc += (i * i) % 97;
    }

    std::printf("{\"ok\": true, \"n\": %ld, \"result\": %lld}\n", n, acc);
    return 0;
}
