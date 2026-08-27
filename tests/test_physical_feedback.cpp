#include "muiFoam/PhysicalFeedback.hpp"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <string>

namespace
{

void require(const bool condition, const char* message)
{
    if (!condition)
    {
        throw std::runtime_error(message);
    }
}

}

int main()
{
    const std::string csv = "gate3d-core-test.csv";
    {
        std::ofstream output(csv.c_str());
        output << "face,theta,area,reference_q,reference_q_ci95,hybrid_q,"
               << "reference_drag_density,reference_drag_ci95,hybrid_drag_density\n";
        for (int face = 0; face < 64; ++face)
        {
            output << face << ',' << (face + 0.5)*0.01 << ",2.5e-6,"
                   << 1000.0 + face << ",10," << 1010.0 + face << ','
                   << 20.0 + face << ",1," << 20.2 + face << '\n';
        }
    }
    const std::vector<muiFoam::PhysicalWallSample> samples =
        muiFoam::readGate3CComparison(csv);
    require(samples.size() == 64, "physical CSV size");
    const double qScale = muiFoam::robustScale(samples, true);
    const double dScale = muiFoam::robustScale(samples, false);
    const double indicator = muiFoam::physicalDiscrepancyIndicator
    (
        samples.front(), qScale, dScale
    );
    require(indicator >= 0.0 && std::isfinite(indicator), "indicator");
    require(muiFoam::physicalLayersAtWindow(0.0, 0) == 5, "first contraction");
    require(muiFoam::physicalLayersAtWindow(0.0, 4) == 4, "bounded contraction");
    require(muiFoam::physicalLayersAtWindow(10.0, 0) == 7, "first expansion");
    require(muiFoam::physicalLayersAtWindow(10.0, 4) == 8, "bounded expansion");

    const muiFoam::ConservativeFlux flux =
        muiFoam::physicalIntegratedFlux(samples.front(), 5.0e-5);
    require(flux[0] == 0.0 && flux[2] == 0.0 && flux[3] == 0.0, "flux components");
    require(flux[1] > 0.0 && flux[4] > 0.0, "physical flux signs");

    muiFoam::PhysicalFeedbackState state;
    state.lastWindow = 2;
    state.activeLayers.assign(64, 6);
    state.faces.assign(64, flux);
    const std::string restart = "gate3d-core-test.state";
    muiFoam::writePhysicalFeedbackState(restart, state);
    const muiFoam::PhysicalFeedbackState restored =
        muiFoam::readPhysicalFeedbackState(restart, 64);
    require(restored.lastWindow == 2, "restart window");
    require(restored.activeLayers == state.activeLayers, "restart layers");
    require(restored.faces == state.faces, "restart flux");
    std::remove(csv.c_str());
    std::remove(restart.c_str());
    return 0;
}
