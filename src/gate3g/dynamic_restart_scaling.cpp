// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/DynamicParticleDomain.hpp"

#include <mpi.h>

#include <algorithm>
#include <cstdlib>
#include <iomanip>
#include <iostream>

namespace
{

constexpr int angularCells = 64;
constexpr int iterations = 250000;

} // namespace

int main(int argc, char** argv)
{
    MPI_Init(&argc, &argv);
    int rank = 0;
    int ranks = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &ranks);

    MPI_Barrier(MPI_COMM_WORLD);
    const double start = MPI_Wtime();
    long long localChecksum = 0;
    long long localMaximumBalanceError = 0;
    for (int iteration = 0; iteration < iterations; ++iteration)
    {
        for (int point = rank; point < angularCells; point += ranks)
        {
            const int requestedLayers = 4 + (iteration + point)%5;
            const int activeLayers =
                muiFoam::activeKineticLayers(requestedLayers);
            muiFoam::ParticleOwnershipLedger ledger;
            ledger.initialParcels = 80 + point;
            ledger.reservoirInserted = (iteration + point)%7;
            ledger.transitionSeeded = (iteration + 2*point)%5;
            ledger.removed = (iteration + 3*point)%4;
            ledger.finalParcels = muiFoam::expectedFinalParcels(ledger);
            localMaximumBalanceError = std::max
            (
                localMaximumBalanceError,
                muiFoam::particleOwnershipBalanceError(ledger)
            );
            localChecksum +=
                static_cast<long long>(point + 1)*activeLayers
              + ledger.finalParcels;
        }
    }
    long long checksum = 0;
    long long maximumBalanceError = 0;
    MPI_Allreduce
    (
        &localChecksum, &checksum, 1, MPI_LONG_LONG, MPI_SUM,
        MPI_COMM_WORLD
    );
    MPI_Allreduce
    (
        &localMaximumBalanceError, &maximumBalanceError, 1,
        MPI_LONG_LONG, MPI_MAX, MPI_COMM_WORLD
    );
    MPI_Barrier(MPI_COMM_WORLD);
    const double elapsed = MPI_Wtime() - start;

    if (rank == 0)
    {
        std::cout << std::setprecision(17)
                  << "GATE3G_SCALING ranks=" << ranks
                  << " iterations=" << iterations
                  << " wall_seconds=" << elapsed
                  << " checksum=" << checksum
                  << " ownership_balance_error=" << maximumBalanceError
                  << '\n';
    }
    MPI_Finalize();
    return maximumBalanceError == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
