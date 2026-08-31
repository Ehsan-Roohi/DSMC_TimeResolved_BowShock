#include "muiFoam/KnGlInterface.hpp"
#include <cassert>
#include <cmath>
#include <vector>
int main()
{
    const double lambda = muiFoam::hardSphereMeanFreePath
    (10.0, 300.0, 4.17e-10, 1.380649e-23);
    assert(std::isfinite(lambda) && lambda > 0.0);
    const double kn = muiFoam::combinedGradientLengthKn
    (0.01, 2.0, 10.0, 300.0, 60.0, 500.0, 4000.0);
    assert(std::abs(kn - 0.08) < 1.0e-14);
    std::vector<double> profile(8, 0.01); profile[5] = 0.08;
    muiFoam::KnGlLayerDecision expand = muiFoam::knGlLayerDecision(profile, 4);
    assert(expand.requestedLayers == 7 && expand.currentLayers == 5);
    std::fill(profile.begin(), profile.end(), 0.01);
    muiFoam::KnGlLayerDecision contract = muiFoam::knGlLayerDecision(profile, 7);
    assert(contract.requestedLayers == 4 && contract.currentLayers == 6);
    profile[4] = 0.04;
    muiFoam::KnGlLayerDecision retain = muiFoam::knGlLayerDecision(profile, 6);
    assert(retain.currentLayers == 6);
}
