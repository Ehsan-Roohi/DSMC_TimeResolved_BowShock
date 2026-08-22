// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_BREAKDOWN_INDICATOR_HPP
#define MUIFOAM_BREAKDOWN_INDICATOR_HPP

#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <limits>

namespace muiFoam
{

inline double safeGradientLengthKn
(
    const double meanFreePath,
    const double fieldMagnitude,
    const double gradientMagnitude,
    const double normalizationFloor
)
{
    if (!std::isfinite(meanFreePath)
     || !std::isfinite(fieldMagnitude)
     || !std::isfinite(gradientMagnitude)
     || meanFreePath < 0.0
     || gradientMagnitude < 0.0
     || normalizationFloor <= 0.0)
    {
        return std::numeric_limits<double>::infinity();
    }

    const double denominator =
        std::max(std::abs(fieldMagnitude), normalizationFloor);

    return meanFreePath*gradientMagnitude/denominator;
}

inline double combinedBreakdown(std::initializer_list<double> indicators)
{
    double result = 0.0;
    for (std::initializer_list<double>::const_iterator iter = indicators.begin();
         iter != indicators.end(); ++iter)
    {
        if (!std::isfinite(*iter) || *iter < 0.0)
        {
            return std::numeric_limits<double>::infinity();
        }
        result = std::max(result, *iter);
    }
    return result;
}

struct HysteresisDecision
{
    enum Value
    {
        retainContinuum,
        activateKinetic,
        retainKinetic,
        deactivateKinetic
    };
};

inline HysteresisDecision::Value classifyWithHysteresis
(
    const double indicator,
    const bool kineticWasActive,
    const double activateThreshold,
    const double deactivateThreshold
)
{
    if (!(deactivateThreshold < activateThreshold)
     || !std::isfinite(indicator))
    {
        return HysteresisDecision::activateKinetic;
    }

    if (kineticWasActive)
    {
        return indicator < deactivateThreshold
             ? HysteresisDecision::deactivateKinetic
             : HysteresisDecision::retainKinetic;
    }

    return indicator > activateThreshold
         ? HysteresisDecision::activateKinetic
         : HysteresisDecision::retainContinuum;
}

} // namespace muiFoam

#endif
