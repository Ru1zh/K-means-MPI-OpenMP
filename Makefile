CXX = c++
MPICXX ?= mpicxx
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic
OMPFLAGS ?= -fopenmp
OMPLIBS ?= -fopenmp
SOURCES = src/main.cpp src/data.cpp src/accumulation.cpp
HEADERS = src/core.hpp src/runtime.hpp src/output.hpp

.PHONY: all serial parallel test test-mpi
all: serial parallel
serial: build/kmeans_serial
parallel: build/kmeans_mpi

build:
	mkdir -p build
build/kmeans_serial: $(SOURCES) $(HEADERS) | build
	$(CXX) $(CXXFLAGS) $(SOURCES) -o $@
build/kmeans_mpi: $(SOURCES) $(HEADERS) | build
	$(MPICXX) $(CXXFLAGS) $(OMPFLAGS) -DKM_MPI $(SOURCES) $(OMPLIBS) -o $@
test: serial
	python3 -m unittest discover -s tests -v
test-mpi: all
	TEST_MPI=1 python3 -m unittest discover -s tests -v

# Optional CUDA build. CPU builds and tests have no CUDA dependency.
NVCC ?= nvcc
CUDA_HOME ?= /usr/local/cuda
CUDA_ARCH ?= 75
NVCCFLAGS ?= -O3 -std=c++17 --fmad=false
.PHONY: cuda test-cuda
cuda: build/kmeans_cuda
build/cuda_backend.o: src/cuda_backend.cu src/cuda_backend.hpp src/core.hpp src/output.hpp | build
	$(NVCC) $(NVCCFLAGS) -arch=sm_$(CUDA_ARCH) -c $< -o $@
build/kmeans_cuda: $(SOURCES) $(HEADERS) src/cuda_backend.hpp build/cuda_backend.o | build
	$(MPICXX) $(CXXFLAGS) $(OMPFLAGS) -DKM_MPI -DKM_CUDA $(SOURCES) build/cuda_backend.o $(OMPLIBS) -L$(CUDA_HOME)/lib64 -Wl,-rpath,$(CUDA_HOME)/lib64 -lcudart -o $@
test-cuda: all cuda
	TEST_CUDA=1 python3 -m unittest discover -s tests -p 'test_cuda.py' -v
