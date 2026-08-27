// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/DynamicParticleDomain.hpp"

#include <cmath>
#include <stdexcept>

namespace
{

void require(const bool condition, const char* message)
{
    if (!condition)
    {
        throw std::runtime_error(message);
    }
}

} // namespace

int main()
{
    require(muiFoam::activeKineticLayers(4) == 2, "four-layer map");
    require(muiFoam::activeKineticLayers(5) == 3, "five-layer map");
    require(muiFoam::activeKineticLayers(6) == 3, "six-layer map");
    require(muiFoam::activeKineticLayers(7) == 4, "seven-layer map");
    require(muiFoam::activeKineticLayers(8) == 4, "eight-layer map");
    require(muiFoam::particleCellActive(2, 5), "activated cell");
    require(!muiFoam::particleCellActive(3, 5), "inactive cell");
    require
    (
        std::abs
        (
            muiFoam::snappedParticleInterfaceRadius(7, 0.01, 0.0025)
          - 0.02
        ) < 1.0e-15,
        "snapped radius"
    );
    require(muiFoam::momentPacketGroups(11.9) == 2, "packet rounding");

    muiFoam::ParticleOwnershipLedger ledger;
    ledger.initialParcels = 100;
    ledger.reservoirInserted = 30;
    ledger.transitionSeeded = 12;
    ledger.removed = 17;
    ledger.finalParcels = 125;
    require(muiFoam::particleOwnershipBalanceError(ledger) == 0, "ledger");
    ledger.finalParcels = 124;
    require(muiFoam::particleOwnershipBalanceError(ledger) == 1, "bad ledger");

    bool rejected = false;
    try
    {
        static_cast<void>(muiFoam::activeKineticLayers(9));
    }
    catch (const std::runtime_error&)
    {
        rejected = true;
    }
    require(rejected, "invalid layers accepted");
    return 0;
}
