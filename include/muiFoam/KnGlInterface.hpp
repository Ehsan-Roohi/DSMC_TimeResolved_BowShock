// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_KNGL_INTERFACE_HPP
#define MUIFOAM_KNGL_INTERFACE_HPP

#include "muiFoam/AdaptiveInterface.hpp"
#include "muiFoam/BreakdownIndicator.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>

namespace muiFoam
{
inline double hardSphereMeanFreePath
(
    const double pressure, const double temperature,
    const double diameter, const double boltzmann
)
{
    if (!std::isfinite(pressure) || pressure <= 0.0
     || !std::isfinite(temperature) || temperature <= 0.0
     || !std::isfinite(diameter) || diameter <= 0.0
     || !std::isfinite(boltzmann) || boltzmann <= 0.0)
    {
        return std::numeric_limits<double>::infinity();
    }
    const double numberDensity = pressure/(boltzmann*temperature);
    return 1.0/(std::sqrt(2.0)*std::acos(-1.0)*diameter*diameter*numberDensity);
}

inline double combinedGradientLengthKn
(
    const double lambda,
    const double density, const double densityGradient,
    const double temperature, const double temperatureGradient,
    const double velocityScale, const double velocityGradient
)
{
    return combinedBreakdown
    ({
        safeGradientLengthKn(lambda, density, densityGradient, 1.0e-300),
        safeGradientLengthKn(lambda, temperature, temperatureGradient, 1.0e-300),
        safeGradientLengthKn(lambda, velocityScale, velocityGradient, 1.0e-300)
    });
}

struct KnGlLayerDecision
{
    int previousLayers;
    int requestedLayers;
    int currentLayers;
    double maximumKnGl;
    bool activationThresholdExceeded;
};

inline KnGlLayerDecision knGlLayerDecision
(
    const std::vector<double>& radialKnGl,
    const int previousLayers,
    const double activateThreshold = 0.05,
    const double deactivateThreshold = 0.03,
    const int minimumLayers = 4,
    const int maximumLayers = 8,
    const int bufferLayers = 1
)
{
    if (radialKnGl.size() < static_cast<std::size_t>(maximumLayers)
     || !(0.0 < deactivateThreshold && deactivateThreshold < activateThreshold)
     || previousLayers < minimumLayers || previousLayers > maximumLayers)
    {
        throw std::runtime_error("invalid Kn_GL interface input");
    }
    int outerActivate = 0;
    int outerRetain = 0;
    double maximum = 0.0;
    for (int layer = 1; layer <= maximumLayers; ++layer)
    {
        const double value = radialKnGl[layer - 1];
        if (!std::isfinite(value) || value < 0.0)
        {
            throw std::runtime_error("invalid Kn_GL radial profile");
        }
        maximum = std::max(maximum, value);
        if (value >= activateThreshold) outerActivate = layer;
        if (value >= deactivateThreshold) outerRetain = layer;
    }
    const int activationTarget = std::max
    (
        minimumLayers, std::min(maximumLayers, outerActivate + bufferLayers)
    );
    const int retentionTarget = std::max
    (
        minimumLayers, std::min(maximumLayers, outerRetain + bufferLayers)
    );
    int requested = previousLayers;
    if (activationTarget > previousLayers) requested = activationTarget;
    else if (retentionTarget < previousLayers) requested = retentionTarget;
    const InterfaceTransition transition = limitedInterfaceTransition
    (
        previousLayers, requested, minimumLayers, maximumLayers, 1
    );
    KnGlLayerDecision result;
    result.previousLayers = previousLayers;
    result.requestedLayers = requested;
    result.currentLayers = transition.currentLayers;
    result.maximumKnGl = maximum;
    result.activationThresholdExceeded = outerActivate > 0;
    return result;
}
}
#endif
