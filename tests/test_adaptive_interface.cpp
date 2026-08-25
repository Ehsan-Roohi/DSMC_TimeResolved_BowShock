// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/AdaptiveInterface.hpp"

#include <cassert>
#include <cmath>
#include <stdexcept>

int main()
{
    const muiFoam::InterfaceTransition grow =
        muiFoam::limitedInterfaceTransition(2, 5, 1, 6);
    assert(grow.currentLayers == 3);
    assert(grow.activatedLayers == 1);
    assert(grow.deactivatedLayers == 0);
    assert(grow.retainedLayers == 2);

    const muiFoam::InterfaceTransition shrink =
        muiFoam::limitedInterfaceTransition(4, 1, 1, 6);
    assert(shrink.currentLayers == 3);
    assert(shrink.activatedLayers == 0);
    assert(shrink.deactivatedLayers == 1);
    assert(shrink.retainedLayers == 3);

    const double pi = std::acos(-1.0);
    double area = 0.0;
    for (int face = 0; face < 32; ++face)
    {
        area += muiFoam::cylindricalFaceArea(0.02, pi/32.0, 0.001);
    }
    assert(std::abs(area - pi*0.02*0.001) < 1.0e-16);

    muiFoam::MovingBoundaryBalance balance;
    balance.initial = {{10.0, 20.0, 0.0, 0.0, 100.0}};
    balance.boundaryExchange = {{1.0, 2.0, 0.5, 0.0, 10.0}};
    balance.sweptInterfaceExchange = {{-0.25, -0.5, 0.0, 0.0, -2.5}};
    balance.final = {{10.75, 21.5, 0.5, 0.0, 107.5}};
    assert(muiFoam::movingBoundaryConservationError(balance) < 1.0e-15);

    bool rejected = false;
    try
    {
        (void)muiFoam::limitedInterfaceTransition(0, 2, 1, 6);
    }
    catch (const std::runtime_error&)
    {
        rejected = true;
    }
    assert(rejected);

    rejected = false;
    try
    {
        (void)muiFoam::cylindricalFaceArea(-1.0, 0.1, 0.001);
    }
    catch (const std::runtime_error&)
    {
        rejected = true;
    }
    assert(rejected);
    return 0;
}
