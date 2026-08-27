#ifndef Gate3FMui_H
#define Gate3FMui_H

#include "Gate3EMui.H"
#include "muiFoam/DynamicParticleDomain.hpp"

namespace gate3f
{

constexpr int couplingWindows = gate3e::couplingWindows;
constexpr int windowSteps = gate3e::windowSteps;
constexpr int kineticSteps = gate3e::kineticSteps;
constexpr int sampleStride = gate3e::sampleStride;
constexpr int samplesPerWindow = gate3e::samplesPerWindow;

inline double particleInterfaceRadius(const int continuumLayers)
{
    return muiFoam::snappedParticleInterfaceRadius
    (
        continuumLayers,
        gate3c::cylinderRadius,
        gate3c::kineticRadialWidth
    );
}

inline mui::point3d particleInterfacePoint
(
    const int pointIndex,
    const int continuumLayers,
    const double inwardOffset = 0.0
)
{
    const double theta = gate3c::centreAngle(pointIndex);
    const double radius = particleInterfaceRadius(continuumLayers)
        - inwardOffset;
    return gate3c::makePoint
    (
        radius*std::cos(theta),
        radius*std::sin(theta),
        0.0
    );
}

} // namespace gate3f

#endif
