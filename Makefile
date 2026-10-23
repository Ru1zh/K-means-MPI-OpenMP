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
