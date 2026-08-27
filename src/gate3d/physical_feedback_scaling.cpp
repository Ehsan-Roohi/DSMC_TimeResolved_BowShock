// SPDX-License-Identifier: GPL-3.0-or-later
#include "mpi.h"

#include "muiFoam/PhysicalFeedback.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char** argv)
{
    MPI_Init(&argc, &argv);
    int rank = 0;
    int ranks = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &ranks);
    int status = EXIT_SUCCESS;
    try
    {
        if (argc != 2 || (ranks != 1 && ranks != 2 && ranks != 4))
        {
            throw std::runtime_error
            (
                "usage: physical_feedback_scaling comparison.csv on 1, 2, or 4 ranks"
            );
        }
        const std::vector<muiFoam::PhysicalWallSample> samples =
            muiFoam::readGate3CComparison(argv[1]);
        const int iterations = 20000;
        volatile double sink = 0.0;
        muiFoam::ConservativeFlux local = muiFoam::zeroFlux();
        MPI_Barrier(MPI_COMM_WORLD);
        const double start = MPI_Wtime();
        for (int iteration = 0; iteration < iterations; ++iteration)
        {
            local = muiFoam::zeroFlux();
            for (std::size_t face = rank; face < samples.size(); face += ranks)
            {
                const muiFoam::ConservativeFlux flux =
                    muiFoam::physicalIntegratedFlux(samples[face], 5.0e-5);
                for (std::size_t component = 0;
                     component < local.size(); ++component)
                {
                    local[component] += flux[component];
                }
            }
            sink += local[1]*1.0e-300 + local[4]*1.0e-300;
        }
        muiFoam::ConservativeFlux global = muiFoam::zeroFlux();
        MPI_Reduce
        (
            local.data(), global.data(), static_cast<int>(global.size()),
            MPI_DOUBLE, MPI_SUM, 0, MPI_COMM_WORLD
        );
        const double localElapsed = MPI_Wtime() - start;
        double elapsed = 0.0;
        MPI_Reduce
        (
            &localElapsed, &elapsed, 1, MPI_DOUBLE, MPI_MAX, 0,
            MPI_COMM_WORLD
        );
        if (rank == 0)
        {
            std::cout << std::setprecision(17)
                      << "GATE3D_SCALING ranks=" << ranks
                      << " iterations=" << iterations
                      << " wall_seconds=" << elapsed
                      << " mass=" << global[0]
                      << " momentum_x=" << global[1]
                      << " momentum_y=" << global[2]
                      << " momentum_z=" << global[3]
                      << " energy=" << global[4]
                      << " sink=" << sink << std::endl;
        }
    }
    catch (const std::exception& error)
    {
        if (rank == 0)
        {
            std::cerr << "GATE3D_SCALING_FAIL reason=" << error.what()
                      << std::endl;
        }
        status = EXIT_FAILURE;
    }
    MPI_Finalize();
    return status;
}
