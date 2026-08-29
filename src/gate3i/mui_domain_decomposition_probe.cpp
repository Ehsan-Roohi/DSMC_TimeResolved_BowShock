// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

#include <mpi.h>

namespace
{

bool close(const double left, const double right)
{
    const double scale = std::max(1.0, std::max(std::abs(left), std::abs(right)));
    return std::abs(left - right) <= 1.0e-12*scale;
}

mui::point3d rankPoint(const int localRank)
{
    mui::point3d point;
    point[0] = 0.125 + 0.25*localRank;
    point[1] = 0.5;
    point[2] = 0.5;
    return point;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 4)
    {
        std::cerr << "Usage: mui_domain_decomposition_probe "
                  << "mpi://domain/session continuum|dsmc RANKS" << std::endl;
        return EXIT_FAILURE;
    }

    const std::string role(argv[2]);
    const int ranks = std::atoi(argv[3]);
    if ((role != "continuum" && role != "dsmc") || ranks < 1 || ranks > 4)
    {
        std::cerr << "GATE3I_FAIL reason=invalid_arguments" << std::endl;
        return EXIT_FAILURE;
    }

    mui::uniface3d interface(argv[1]);
    int worldRank = -1;
    int worldSize = 0;
    MPI_Comm_rank(MPI_COMM_WORLD, &worldRank);
    MPI_Comm_size(MPI_COMM_WORLD, &worldSize);
    const int localRank = worldRank % ranks;
    if (worldSize != 2*ranks)
    {
        std::cerr << "GATE3I_FAIL reason=world_size expected=" << 2*ranks
                  << " actual=" << worldSize << std::endl;
        return EXIT_FAILURE;
    }

    const mui::point3d point = rankPoint(localRank);
    const double outgoing = (role == "continuum" ? 1000.0 : 2000.0) + localRank;
    const char* outgoingName = role == "continuum" ? "forward" : "reverse";
    const char* incomingName = role == "continuum" ? "reverse" : "forward";
    const double expected = (role == "continuum" ? 2000.0 : 1000.0) + localRank;
    interface.push(outgoingName, point, outgoing);
    interface.commit(0);

    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    const double received = interface.fetch
    (
        incomingName, point, 0, spatialSampler, temporalSampler
    );
    if (!close(received, expected))
    {
        std::cerr << "GATE3I_FAIL reason=transport role=" << role
                  << " local_rank=" << localRank
                  << " expected=" << expected
                  << " actual=" << received << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << "GATE3I_MUI_PASS role=" << role
              << " local_rank=" << localRank
              << " app_ranks=" << ranks
              << " world_ranks=" << worldSize
              << " bidirectional=true" << std::endl;
    return EXIT_SUCCESS;
}
