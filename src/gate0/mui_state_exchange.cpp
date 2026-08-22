// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

#include "muiFoam/CouplingState.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

namespace
{

const int nPoints = 3;

muiFoam::CouplingState referenceState(const int i)
{
    muiFoam::CouplingState state;
    state.rho = 1.0 + 0.1*i;
    state.ux = 1200.0 + 50.0*i;
    state.uy = -20.0 + 5.0*i;
    state.uz = 0.0;
    state.temperature = 300.0 + 25.0*i;
    return state;
}

mui::point2d point(const int i)
{
    mui::point2d p;
    p[0] = 0.25*i;
    p[1] = 0.5;
    return p;
}

bool close(const double a, const double b)
{
    const double scale = std::max(1.0, std::max(std::abs(a), std::abs(b)));
    return std::abs(a - b) <= 1.0e-12*scale;
}

void pushState(mui::uniface2d& interface)
{
    for (int i = 0; i < nPoints; ++i)
    {
        const muiFoam::CouplingState state = referenceState(i);
        const mui::point2d p = point(i);
        interface.push("rho", p, state.rho);
        interface.push("Ux", p, state.ux);
        interface.push("Uy", p, state.uy);
        interface.push("Uz", p, state.uz);
        interface.push("T", p, state.temperature);
    }
}

int checkState(mui::uniface2d& interface)
{
    mui::sampler_exact2d<double> spatialSampler;
    mui::temporal_sampler_exact2d temporalSampler;
    const int time = 0;

    for (int i = 0; i < nPoints; ++i)
    {
        const mui::point2d p = point(i);
        muiFoam::CouplingState actual;
        actual.rho = interface.fetch("rho", p, time, spatialSampler, temporalSampler);
        actual.ux = interface.fetch("Ux", p, time, spatialSampler, temporalSampler);
        actual.uy = interface.fetch("Uy", p, time, spatialSampler, temporalSampler);
        actual.uz = interface.fetch("Uz", p, time, spatialSampler, temporalSampler);
        actual.temperature = interface.fetch("T", p, time, spatialSampler, temporalSampler);

        const muiFoam::CouplingState expected = referenceState(i);
        if (!actual.physical()
         || !close(actual.rho, expected.rho)
         || !close(actual.ux, expected.ux)
         || !close(actual.uy, expected.uy)
         || !close(actual.uz, expected.uz)
         || !close(actual.temperature, expected.temperature))
        {
            std::cerr << "Gate-0 state mismatch at point " << i << std::endl;
            return EXIT_FAILURE;
        }
    }

    return EXIT_SUCCESS;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 3)
    {
        std::cerr << "Usage: mui_state_exchange mpi://domain/interface "
                  << "continuum|dsmc" << std::endl;
        return EXIT_FAILURE;
    }

    const std::string role(argv[2]);
    if (role != "continuum" && role != "dsmc")
    {
        std::cerr << "Unknown role: " << role << std::endl;
        return EXIT_FAILURE;
    }

    mui::uniface2d interface(argv[1]);
    const mui::point2d origin = point(0);

    if (role == "continuum")
    {
        pushState(interface);
        interface.push("receiverReady", origin, 0.0);
    }
    else
    {
        interface.push("receiverReady", origin, 1.0);
    }

    interface.commit(0);

    mui::sampler_exact2d<double> spatialSampler;
    mui::temporal_sampler_exact2d temporalSampler;

    if (role == "continuum")
    {
        const double ready = interface.fetch
        (
            "receiverReady", origin, 0, spatialSampler, temporalSampler
        );
        if (!close(ready, 1.0))
        {
            std::cerr << "Gate-0 receiver handshake failed" << std::endl;
            return EXIT_FAILURE;
        }
    }
    else if (checkState(interface) != EXIT_SUCCESS)
    {
        return EXIT_FAILURE;
    }

    std::cout << "GATE0_PASS role=" << role << std::endl;
    return EXIT_SUCCESS;
}
