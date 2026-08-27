// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_DYNAMIC_PARTICLE_DOMAIN_HPP
#define MUIFOAM_DYNAMIC_PARTICLE_DOMAIN_HPP

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <stdexcept>

namespace muiFoam
{

constexpr int minimumContinuumLayers = 4;
constexpr int maximumContinuumLayers = 8;
constexpr int kineticMeshLayers = 6;

inline int activeKineticLayers(const int continuumLayers)
{
    if
    (
        continuumLayers < minimumContinuumLayers
     || continuumLayers > maximumContinuumLayers
    )
    {
        throw std::runtime_error("invalid dynamic particle-domain layer count");
    }

    // The Gate 3C DSMC annulus has twice the radial spacing of the continuum.
    // Snap the moving continuum request outward to the next DSMC cell face.
    return std::min(kineticMeshLayers, (continuumLayers + 1)/2);
}

inline bool particleCellActive
(
    const int kineticLayer,
    const int continuumLayers
)
{
    if (kineticLayer < 0 || kineticLayer >= kineticMeshLayers)
    {
        throw std::runtime_error("invalid DSMC radial layer");
    }
    return kineticLayer < activeKineticLayers(continuumLayers);
}

inline double snappedParticleInterfaceRadius
(
    const int continuumLayers,
    const double cylinderRadius,
    const double kineticRadialWidth
)
{
    if
    (
        !std::isfinite(cylinderRadius) || cylinderRadius <= 0.0
     || !std::isfinite(kineticRadialWidth) || kineticRadialWidth <= 0.0
    )
    {
        throw std::runtime_error("invalid dynamic particle-domain geometry");
    }
    return cylinderRadius
        + activeKineticLayers(continuumLayers)*kineticRadialWidth;
}

struct ParticleOwnershipLedger
{
    long long initialParcels = 0;
    long long reservoirInserted = 0;
    long long transitionSeeded = 0;
    long long removed = 0;
    long long finalParcels = 0;
};

inline long long expectedFinalParcels(const ParticleOwnershipLedger& ledger)
{
    if
    (
        ledger.initialParcels < 0
     || ledger.reservoirInserted < 0
     || ledger.transitionSeeded < 0
     || ledger.removed < 0
     || ledger.finalParcels < 0
    )
    {
        throw std::runtime_error("negative dynamic particle-domain ledger");
    }
    return ledger.initialParcels
        + ledger.reservoirInserted
        + ledger.transitionSeeded
        - ledger.removed;
}

inline long long particleOwnershipBalanceError
(
    const ParticleOwnershipLedger& ledger
)
{
    return std::llabs(ledger.finalParcels - expectedFinalParcels(ledger));
}

inline long long momentPacketGroups(const double expectedParcels)
{
    if (!std::isfinite(expectedParcels) || expectedParcels <= 0.0)
    {
        throw std::runtime_error("invalid activated-cell parcel population");
    }
    return std::max
    (
        1LL,
        static_cast<long long>(std::floor(expectedParcels/6.0 + 0.5))
    );
}

} // namespace muiFoam

#endif
