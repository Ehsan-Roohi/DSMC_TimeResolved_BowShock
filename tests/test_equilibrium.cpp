// SPDX-License-Identifier: GPL-3.0-or-later
#include "muiFoam/EquilibriumAudit.hpp"

#include <cassert>

int main()
{
    muiFoam::CouplingState state;
    state.rho = 1.225;
    state.ux = 350.0;
    state.uy = -12.0;
    state.uz = 4.0;
    state.temperature = 300.0;

    const double argonMass = 6.6335209e-26;
    const double volume = 2.5e-6;
    const std::array<muiFoam::WeightedParticle, 6> packet =
        muiFoam::momentExactMaxwellianPacket(state, argonMass, volume);
    const muiFoam::ConservedMoments actual =
        muiFoam::packetMoments(packet);
    const muiFoam::ConservedMoments expected =
        muiFoam::equilibriumMoments(state, argonMass, volume);

    assert(state.physical());
    assert(muiFoam::maximumMomentError(actual, expected) < 2.0e-15);
    return 0;
}
