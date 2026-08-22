// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_EQUILIBRIUM_AUDIT_HPP
#define MUIFOAM_EQUILIBRIUM_AUDIT_HPP

#include "muiFoam/CouplingState.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace muiFoam
{

const double boltzmannConstant = 1.380649e-23;

struct WeightedParticle
{
    std::array<double, 3> velocity;
    double molecularMass;
    double statisticalWeight;
};

struct ConservedMoments
{
    double mass;
    std::array<double, 3> momentum;
    double totalEnergy;

    ConservedMoments()
    :
        mass(0.0),
        momentum{{0.0, 0.0, 0.0}},
        totalEnergy(0.0)
    {}
};

inline std::array<WeightedParticle, 6> momentExactMaxwellianPacket
(
    const CouplingState& state,
    const double molecularMass,
    const double representedVolume
)
{
    std::array<WeightedParticle, 6> packet;
    const double thermalComponent = std::sqrt
    (
        3.0*boltzmannConstant*state.temperature/molecularMass
    );
    const double weight =
        state.rho*representedVolume/(6.0*molecularMass);
    const double bulk[3] = {state.ux, state.uy, state.uz};

    for (int axis = 0; axis < 3; ++axis)
    {
        for (int signIndex = 0; signIndex < 2; ++signIndex)
        {
            const int particleIndex = 2*axis + signIndex;
            WeightedParticle& particle = packet[particleIndex];
            particle.molecularMass = molecularMass;
            particle.statisticalWeight = weight;
            particle.velocity = {{bulk[0], bulk[1], bulk[2]}};
            particle.velocity[axis] +=
                (signIndex == 0 ? -thermalComponent : thermalComponent);
        }
    }

    return packet;
}

inline ConservedMoments packetMoments
(
    const std::array<WeightedParticle, 6>& packet
)
{
    ConservedMoments result;
    for (std::size_t i = 0; i < packet.size(); ++i)
    {
        const WeightedParticle& particle = packet[i];
        const double representedMass =
            particle.statisticalWeight*particle.molecularMass;
        result.mass += representedMass;

        double speedSquared = 0.0;
        for (int component = 0; component < 3; ++component)
        {
            result.momentum[component] +=
                representedMass*particle.velocity[component];
            speedSquared +=
                particle.velocity[component]*particle.velocity[component];
        }
        result.totalEnergy += 0.5*representedMass*speedSquared;
    }
    return result;
}

inline ConservedMoments equilibriumMoments
(
    const CouplingState& state,
    const double molecularMass,
    const double representedVolume
)
{
    ConservedMoments result;
    result.mass = state.rho*representedVolume;
    result.momentum[0] = result.mass*state.ux;
    result.momentum[1] = result.mass*state.uy;
    result.momentum[2] = result.mass*state.uz;

    const double bulkSpeedSquared =
        state.ux*state.ux + state.uy*state.uy + state.uz*state.uz;
    const double moleculeCount = result.mass/molecularMass;
    result.totalEnergy =
        0.5*result.mass*bulkSpeedSquared
      + 1.5*moleculeCount*boltzmannConstant*state.temperature;
    return result;
}

inline double normalizedDifference
(
    const double actual,
    const double expected,
    const double floor = 1.0e-300
)
{
    if (!std::isfinite(actual) || !std::isfinite(expected))
    {
        return std::numeric_limits<double>::infinity();
    }
    return std::abs(actual - expected)/std::max(std::abs(expected), floor);
}

inline double maximumMomentError
(
    const ConservedMoments& actual,
    const ConservedMoments& expected
)
{
    double error = normalizedDifference(actual.mass, expected.mass);
    error = std::max
    (
        error,
        normalizedDifference(actual.totalEnergy, expected.totalEnergy)
    );
    for (int component = 0; component < 3; ++component)
    {
        const double scale = std::max
        (
            std::abs(expected.momentum[component]),
            expected.mass
        );
        error = std::max
        (
            error,
            std::abs
            (
                actual.momentum[component]
              - expected.momentum[component]
            )/std::max(scale, 1.0e-300)
        );
    }
    return error;
}

} // namespace muiFoam

#endif
