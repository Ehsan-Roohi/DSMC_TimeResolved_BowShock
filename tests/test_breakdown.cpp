// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/BreakdownIndicator.hpp"

#include <cassert>
#include <cmath>
#include <limits>

int main()
{
    using namespace muiFoam;

    assert(std::abs(safeGradientLengthKn(0.01, 2.0, 10.0, 1.0e-12) - 0.05)
        < 1.0e-14);
    assert(std::abs(safeGradientLengthKn(0.01, 0.0, 1.0, 0.5) - 0.02)
        < 1.0e-14);
    assert(!std::isfinite(safeGradientLengthKn(-1.0, 1.0, 1.0, 1.0e-12)));

    assert(std::abs(combinedBreakdown({0.01, 0.08, 0.03}) - 0.08)
        < 1.0e-14);
    assert(!std::isfinite(combinedBreakdown
        ({0.01, std::numeric_limits<double>::quiet_NaN()})));

    assert(classifyWithHysteresis(0.06, false, 0.05, 0.03)
        == HysteresisDecision::activateKinetic);
    assert(classifyWithHysteresis(0.04, false, 0.05, 0.03)
        == HysteresisDecision::retainContinuum);
    assert(classifyWithHysteresis(0.04, true, 0.05, 0.03)
        == HysteresisDecision::retainKinetic);
    assert(classifyWithHysteresis(0.02, true, 0.05, 0.03)
        == HysteresisDecision::deactivateKinetic);

    return 0;
}
