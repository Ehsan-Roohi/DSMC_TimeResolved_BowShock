// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_ADAPTIVE_INTERFACE_HPP
#define MUIFOAM_ADAPTIVE_INTERFACE_HPP

#include "muiFoam/ConservativeFlux.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace muiFoam
{

struct InterfaceTransition
{
    int previousLayers;
    int requestedLayers;
    int currentLayers;
    int activatedLayers;
    int deactivatedLayers;
    int retainedLayers;
};

inline InterfaceTransition limitedInterfaceTransition
(
    const int previousLayers,
    const int requestedLayers,
    const int minimumLayers,
    const int maximumLayers,
    const int maximumLayerChange = 1
)
{
    if (minimumLayers <= 0 || maximumLayers < minimumLayers
     || previousLayers < minimumLayers || previousLayers > maximumLayers
     || requestedLayers < minimumLayers || requestedLayers > maximumLayers
     || maximumLayerChange <= 0)
    {
        throw std::runtime_error("invalid adaptive-interface transition");
    }

    const int lower = std::max(minimumLayers, previousLayers - maximumLayerChange);
    const int upper = std::min(maximumLayers, previousLayers + maximumLayerChange);
    const int current = std::max(lower, std::min(upper, requestedLayers));

    InterfaceTransition transition;
    transition.previousLayers = previousLayers;
    transition.requestedLayers = requestedLayers;
    transition.currentLayers = current;
    transition.activatedLayers = std::max(0, current - previousLayers);
    transition.deactivatedLayers = std::max(0, previousLayers - current);
    transition.retainedLayers = std::min(previousLayers, current);
    return transition;
}

inline double cylindricalFaceArea
(
    const double radius,
    const double angularWidth,
    const double span
)
{
    if (!std::isfinite(radius) || radius <= 0.0
     || !std::isfinite(angularWidth) || angularWidth <= 0.0
     || !std::isfinite(span) || span <= 0.0)
    {
        throw std::runtime_error("invalid cylindrical interface geometry");
    }
    return radius*angularWidth*span;
}

struct MovingBoundaryBalance
{
    ConservativeFlux initial;
    ConservativeFlux boundaryExchange;
    ConservativeFlux sweptInterfaceExchange;
    ConservativeFlux final;
};

inline ConservativeFlux expectedMovingBoundaryFinal
(
    const MovingBoundaryBalance& balance
)
{
    if (!finiteFlux(balance.initial)
     || !finiteFlux(balance.boundaryExchange)
     || !finiteFlux(balance.sweptInterfaceExchange))
    {
        throw std::runtime_error("non-finite moving-boundary balance input");
    }
    ConservativeFlux expected = zeroFlux();
    for (std::size_t component = 0; component < expected.size(); ++component)
    {
        expected[component] = balance.initial[component]
            + balance.boundaryExchange[component]
            + balance.sweptInterfaceExchange[component];
    }
    return expected;
}

inline double movingBoundaryConservationError
(
    const MovingBoundaryBalance& balance
)
{
    if (!finiteFlux(balance.final))
    {
        throw std::runtime_error("non-finite moving-boundary final state");
    }
    return maximumRelativeDifference
    (
        balance.final,
        expectedMovingBoundaryFinal(balance)
    );
}

} // namespace muiFoam

#endif
