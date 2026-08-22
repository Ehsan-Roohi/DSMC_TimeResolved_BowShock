// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

#include "muiFoam/CouplingState.hpp"
#include "muiFoam/EquilibriumAudit.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <string>

namespace
{

const int nFaces = 12;
const double argonMass = 6.6335209e-26;
const double representedVolume = 1.0e-9;

muiFoam::CouplingState uniformState()
{
    muiFoam::CouplingState state;
    state.rho = 1.225;
    state.ux = 350.0;
    state.uy = 0.0;
    state.uz = 0.0;
    state.temperature = 300.0;
    return state;
}

mui::point3d faceCentre(const int faceIndex)
{
    mui::point3d point;
    point[0] = 0.0;
    point[1] = (faceIndex + 0.5)/nFaces;
    point[2] = 0.5;
    return point;
}

bool close(const double a, const double b)
{
    const double scale = std::max(1.0, std::max(std::abs(a), std::abs(b)));
    return std::abs(a - b) <= 1.0e-12*scale;
}

void pushState(mui::uniface3d& interface)
{
    const muiFoam::CouplingState state = uniformState();
    for (int faceIndex = 0; faceIndex < nFaces; ++faceIndex)
    {
        const mui::point3d point = faceCentre(faceIndex);
        interface.push("rho", point, state.rho);
        interface.push("Ux", point, state.ux);
        interface.push("Uy", point, state.uy);
        interface.push("Uz", point, state.uz);
        interface.push("T", point, state.temperature);
    }
}

muiFoam::CouplingState fetchState
(
    mui::uniface3d& interface,
    const mui::point3d& point
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    muiFoam::CouplingState state;
    state.rho = interface.fetch("rho", point, 0, spatialSampler, temporalSampler);
    state.ux = interface.fetch("Ux", point, 0, spatialSampler, temporalSampler);
    state.uy = interface.fetch("Uy", point, 0, spatialSampler, temporalSampler);
    state.uz = interface.fetch("Uz", point, 0, spatialSampler, temporalSampler);
    state.temperature =
        interface.fetch("T", point, 0, spatialSampler, temporalSampler);
    return state;
}

int receiveAndAudit(mui::uniface3d& interface)
{
    const muiFoam::CouplingState expectedState = uniformState();
    double maxStateError = 0.0;
    double maxMomentError = 0.0;

    for (int faceIndex = 0; faceIndex < nFaces; ++faceIndex)
    {
        const muiFoam::CouplingState state =
            fetchState(interface, faceCentre(faceIndex));
        if (!state.physical())
        {
            std::cerr << "Non-physical mapped state at face " << faceIndex
                      << std::endl;
            return EXIT_FAILURE;
        }

        maxStateError = std::max(maxStateError, std::abs(state.rho - expectedState.rho));
        maxStateError = std::max(maxStateError, std::abs(state.ux - expectedState.ux));
        maxStateError = std::max(maxStateError, std::abs(state.uy - expectedState.uy));
        maxStateError = std::max(maxStateError, std::abs(state.uz - expectedState.uz));
        maxStateError = std::max
        (
            maxStateError,
            std::abs(state.temperature - expectedState.temperature)
        );

        const std::array<muiFoam::WeightedParticle, 6> packet =
            muiFoam::momentExactMaxwellianPacket
            (
                state,
                argonMass,
                representedVolume
            );
        const muiFoam::ConservedMoments actual =
            muiFoam::packetMoments(packet);
        const muiFoam::ConservedMoments expected =
            muiFoam::equilibriumMoments
            (
                state,
                argonMass,
                representedVolume
            );
        maxMomentError = std::max
        (
            maxMomentError,
            muiFoam::maximumMomentError(actual, expected)
        );
    }

    std::cout << std::setprecision(17)
              << "GATE1A_TRANSFER_PASS faces=" << nFaces
              << " max_state_abs=" << maxStateError << '\n'
              << "GATE1A_MAXWELLIAN_PASS particles_per_face=6"
              << " max_moment_rel=" << maxMomentError << std::endl;

    return maxStateError <= 1.0e-12 && maxMomentError <= 1.0e-12
         ? EXIT_SUCCESS
         : EXIT_FAILURE;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 3)
    {
        std::cerr << "Usage: mui_fixed_interface mpi://domain/interface "
                  << "continuum|dsmc" << std::endl;
        return EXIT_FAILURE;
    }

    const std::string role(argv[2]);
    if (role != "continuum" && role != "dsmc")
    {
        std::cerr << "Unknown role: " << role << std::endl;
        return EXIT_FAILURE;
    }

    mui::uniface3d interface(argv[1]);
    const mui::point3d origin = faceCentre(0);

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

    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;

    if (role == "continuum")
    {
        const double ready = interface.fetch
        (
            "receiverReady", origin, 0, spatialSampler, temporalSampler
        );
        if (!close(ready, 1.0))
        {
            std::cerr << "Gate-1A receiver handshake failed" << std::endl;
            return EXIT_FAILURE;
        }
        std::cout << "GATE1A_PASS role=continuum faces=" << nFaces << std::endl;
        return EXIT_SUCCESS;
    }

    if (receiveAndAudit(interface) != EXIT_SUCCESS)
    {
        return EXIT_FAILURE;
    }
    std::cout << "GATE1A_PASS role=dsmc faces=" << nFaces << std::endl;
    return EXIT_SUCCESS;
}
