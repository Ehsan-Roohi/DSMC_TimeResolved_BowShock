// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

#include "muiFoam/PhysicalFeedback.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

const int nComponents = 5;
const int nWindows = 5;
const double pi = 3.141592653589793238462643383279502884;
const double cylinderRadius = 0.01;
const double radialLayerWidth = 0.0025;
const double physicalWindowDuration = 5.0e-5;
const char* fluxNames[nComponents] =
{
    "massIntegrated",
    "momentumXIntegrated",
    "momentumYIntegrated",
    "momentumZIntegrated",
    "energyIntegrated"
};
const char* totalNames[nComponents] =
{
    "massTotal",
    "momentumXTotal",
    "momentumYTotal",
    "momentumZTotal",
    "energyTotal"
};

std::vector<int> selectedWindows(const std::string& mode)
{
    if (mode == "continuous") return std::vector<int>{0, 1, 2, 3, 4};
    if (mode == "fresh") return std::vector<int>{0, 1, 2};
    if (mode == "restart") return std::vector<int>{3, 4};
    throw std::runtime_error("unknown Gate-3D segment mode");
}

double relaxation(const int window)
{
    const double values[nWindows] = {0.20, 0.30, 0.40, 0.50, 0.50};
    if (window < 0 || window >= nWindows)
    {
        throw std::runtime_error("invalid Gate-3D window");
    }
    return values[window];
}

mui::point2d metadataPoint()
{
    mui::point2d point;
    point[0] = -1.0;
    point[1] = -1.0;
    return point;
}

mui::point2d interfacePoint
(
    const muiFoam::PhysicalWallSample& sample,
    const int layers
)
{
    if (layers < 4 || layers > 8)
    {
        throw std::runtime_error("invalid Gate-3D interface layer");
    }
    const double radius = cylinderRadius + layers*radialLayerWidth;
    mui::point2d point;
    point[0] = radius*std::cos(sample.theta);
    point[1] = radius*std::sin(sample.theta);
    return point;
}

bool close(const double actual, const double expected, const double tolerance = 1.0e-12)
{
    const double scale = std::max
    (
        1.0,
        std::max(std::abs(actual), std::abs(expected))
    );
    return std::abs(actual - expected) <= tolerance*scale;
}

double normalizedUncertainty
(
    const std::vector<muiFoam::PhysicalWallSample>& samples
)
{
    double qSquared = 0.0;
    double qCiSquared = 0.0;
    double dragSquared = 0.0;
    double dragCiSquared = 0.0;
    for (std::size_t face = 0; face < samples.size(); ++face)
    {
        qSquared += samples[face].referenceHeatFlux
            *samples[face].referenceHeatFlux;
        qCiSquared += samples[face].referenceHeatFluxCi95
            *samples[face].referenceHeatFluxCi95;
        dragSquared += samples[face].referenceDragDensity
            *samples[face].referenceDragDensity;
        dragCiSquared += samples[face].referenceDragCi95
            *samples[face].referenceDragCi95;
    }
    const double tiny = 1.0e-300;
    return std::max
    (
        std::sqrt(qCiSquared)/std::max(std::sqrt(qSquared), tiny),
        std::sqrt(dragCiSquared)/std::max(std::sqrt(dragSquared), tiny)
    );
}

std::vector<double> indicators
(
    const std::vector<muiFoam::PhysicalWallSample>& samples
)
{
    const double qScale = muiFoam::robustScale(samples, true);
    const double dragScale = muiFoam::robustScale(samples, false);
    std::vector<double> result(samples.size(), 0.0);
    for (std::size_t face = 0; face < samples.size(); ++face)
    {
        result[face] = muiFoam::physicalDiscrepancyIndicator
        (
            samples[face], qScale, dragScale
        );
    }
    return result;
}

std::vector<int> layersAtWindow
(
    const std::vector<double>& indicator,
    const int window
)
{
    std::vector<int> layers(indicator.size(), 6);
    for (std::size_t face = 0; face < indicator.size(); ++face)
    {
        layers[face] = muiFoam::physicalLayersAtWindow
        (
            indicator[face], window
        );
    }
    return layers;
}

void publishWindow
(
    mui::uniface2d& interface,
    const int window,
    const std::vector<muiFoam::PhysicalWallSample>& samples,
    const std::vector<double>& indicator
)
{
    const std::vector<int> layers = layersAtWindow(indicator, window);
    std::vector<muiFoam::ConservativeFlux> fluxes(samples.size());
    for (std::size_t face = 0; face < samples.size(); ++face)
    {
        fluxes[face] = muiFoam::physicalIntegratedFlux
        (
            samples[face], physicalWindowDuration
        );
        const mui::point2d point = interfacePoint(samples[face], layers[face]);
        for (int component = 0; component < nComponents; ++component)
        {
            interface.push
            (
                fluxNames[component], point, fluxes[face][component]
            );
        }
    }
    const muiFoam::ConservativeFlux total = muiFoam::totalFlux(fluxes);
    const mui::point2d meta = metadataPoint();
    for (int component = 0; component < nComponents; ++component)
    {
        interface.push(totalNames[component], meta, total[component]);
    }
    interface.push("sampleCount", meta, 200.0);
    interface.push("maximumNormalizedCi95", meta, normalizedUncertainty(samples));
    interface.push("relaxation", meta, relaxation(window));
    interface.push("receiverReady", meta, 0.0);
}

muiFoam::ConservativeFlux fetchTotals
(
    mui::uniface2d& interface,
    const int window,
    mui::sampler_exact2d<double>& exact,
    mui::temporal_sampler_exact2d& temporal
)
{
    muiFoam::ConservativeFlux total = muiFoam::zeroFlux();
    for (int component = 0; component < nComponents; ++component)
    {
        total[component] = interface.fetch
        (
            totalNames[component], metadataPoint(), window, exact, temporal
        );
    }
    return total;
}

int runDsmcReplay
(
    mui::uniface2d& interface,
    const std::string& mode,
    const std::vector<muiFoam::PhysicalWallSample>& samples
)
{
    const std::vector<double> indicator = indicators(samples);
    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;
    const std::vector<int> windows = selectedWindows(mode);
    for (std::size_t index = 0; index < windows.size(); ++index)
    {
        const int window = windows[index];
        publishWindow(interface, window, samples, indicator);
        interface.commit(window);
        const double ready = interface.fetch
        (
            "receiverReady", metadataPoint(), window, exact, temporal
        );
        if (!close(ready, 1.0))
        {
            std::cerr << "GATE3D_FAIL role=dsmc_replay reason=handshake"
                      << " window=" << window << std::endl;
            return EXIT_FAILURE;
        }
    }
    std::cout << "GATE3D_PASS role=dsmc_replay mode=" << mode
              << " physical_source=gate3c_hybrid_wall_statistics"
              << " windows=" << windows.size() << std::endl;
    return EXIT_SUCCESS;
}

void writeFeedbackCsv
(
    const std::string& path,
    const std::vector<muiFoam::PhysicalWallSample>& samples,
    const std::vector<double>& indicator,
    const muiFoam::PhysicalFeedbackState& state
)
{
    std::ofstream output(path.c_str(), std::ios::out | std::ios::trunc);
    if (!output)
    {
        throw std::runtime_error("cannot create Gate-3D feedback CSV");
    }
    output << "face,theta,interface_radius,wall_area,indicator,active_layers,"
           << "mass,momentum_x,momentum_y,momentum_z,energy\n"
           << std::scientific << std::setprecision(17);
    for (std::size_t face = 0; face < samples.size(); ++face)
    {
        const double radius = cylinderRadius
            + state.activeLayers[face]*radialLayerWidth;
        output << samples[face].face << ',' << samples[face].theta << ','
               << radius << ',' << samples[face].area << ','
               << indicator[face] << ',' << state.activeLayers[face];
        for (std::size_t component = 0;
             component < state.faces[face].size(); ++component)
        {
            output << ',' << state.faces[face][component];
        }
        output << '\n';
    }
}

int runContinuum
(
    mui::uniface2d& interface,
    const std::string& mode,
    const std::string& inputState,
    const std::string& outputState,
    const std::string& outputCsv,
    const std::vector<muiFoam::PhysicalWallSample>& samples
)
{
    const std::vector<double> indicator = indicators(samples);
    muiFoam::PhysicalFeedbackState state;
    state.lastWindow = -1;
    state.activeLayers.assign(samples.size(), 6);
    state.faces.assign(samples.size(), muiFoam::zeroFlux());
    if (mode == "restart")
    {
        state = muiFoam::readPhysicalFeedbackState(inputState, samples.size());
        if (state.lastWindow != 2)
        {
            throw std::runtime_error("Gate-3D restart must resume after window 2");
        }
    }

    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;
    double maximumRawError = 0.0;
    double maximumProjectedError = 0.0;
    double maximumRelaxedError = 0.0;
    int activatedLayers = 0;
    int deactivatedLayers = 0;
    const std::vector<int> windows = selectedWindows(mode);
    for (std::size_t index = 0; index < windows.size(); ++index)
    {
        const int window = windows[index];
        interface.push("receiverReady", metadataPoint(), 1.0);
        interface.commit(window);

        const int sampleCount = static_cast<int>(std::lround(interface.fetch
        (
            "sampleCount", metadataPoint(), window, exact, temporal
        )));
        const double uncertainty = interface.fetch
        (
            "maximumNormalizedCi95", metadataPoint(), window, exact, temporal
        );
        const double alpha = interface.fetch
        (
            "relaxation", metadataPoint(), window, exact, temporal
        );
        if
        (
            sampleCount < 200
         || !std::isfinite(uncertainty)
         || uncertainty < 0.0
         || uncertainty > 0.25
        )
        {
            std::cerr << "GATE3D_FAIL role=continuum reason=unresolved_physical_flux"
                      << " window=" << window
                      << " samples=" << sampleCount
                      << " normalized_ci95=" << uncertainty << std::endl;
            return EXIT_FAILURE;
        }

        std::vector<int> currentLayers(samples.size(), 6);
        std::vector<double> faceAreas(samples.size(), 0.0);
        std::vector<muiFoam::ConservativeFlux> mapped
        (
            samples.size(), muiFoam::zeroFlux()
        );
        for (std::size_t face = 0; face < samples.size(); ++face)
        {
            const int requested = muiFoam::requestedPhysicalLayers
            (
                indicator[face]
            );
            const muiFoam::InterfaceTransition transition =
                muiFoam::limitedInterfaceTransition
                (
                    state.activeLayers[face], requested, 4, 8, 1
                );
            currentLayers[face] = transition.currentLayers;
            activatedLayers += transition.activatedLayers;
            deactivatedLayers += transition.deactivatedLayers;
            const mui::point2d point = interfacePoint
            (
                samples[face], currentLayers[face]
            );
            for (int component = 0; component < nComponents; ++component)
            {
                mapped[face][component] = interface.fetch
                (
                    fluxNames[component], point, window, exact, temporal
                );
            }
            faceAreas[face] = samples[face].area;
        }

        const muiFoam::ConservativeFlux sourceTotal = fetchTotals
        (
            interface, window, exact, temporal
        );
        const double rawError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(mapped), sourceTotal
        );
        muiFoam::projectGlobalConservation(mapped, sourceTotal, faceAreas);
        const double projectedError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(mapped), sourceTotal
        );
        const muiFoam::ConservativeFlux previousTotal =
            muiFoam::totalFlux(state.faces);
        for (std::size_t face = 0; face < samples.size(); ++face)
        {
            state.faces[face] = muiFoam::relaxedFlux
            (
                state.faces[face], mapped[face], alpha
            );
        }
        const muiFoam::ConservativeFlux expectedTotal =
            muiFoam::relaxedFlux(previousTotal, sourceTotal, alpha);
        const double relaxedError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(state.faces), expectedTotal
        );
        state.activeLayers = currentLayers;
        state.lastWindow = window;
        maximumRawError = std::max(maximumRawError, rawError);
        maximumProjectedError = std::max
        (
            maximumProjectedError, projectedError
        );
        maximumRelaxedError = std::max(maximumRelaxedError, relaxedError);
        std::cout << std::setprecision(17)
                  << "GATE3D_WINDOW window=" << window
                  << " samples=" << sampleCount
                  << " normalized_ci95=" << uncertainty
                  << " alpha=" << alpha
                  << " activated_layers=" << activatedLayers
                  << " deactivated_layers=" << deactivatedLayers
                  << " raw_conservation_rel=" << rawError
                  << " projected_conservation_rel=" << projectedError
                  << " relaxed_conservation_rel=" << relaxedError
                  << std::endl;
    }

    if
    (
        state.lastWindow != windows.back()
     || outputState == "-"
     || outputCsv == "-"
    )
    {
        throw std::runtime_error("invalid Gate-3D output contract");
    }
    muiFoam::writePhysicalFeedbackState(outputState, state);
    writeFeedbackCsv(outputCsv, samples, indicator, state);
    if
    (
        maximumRawError > 1.0e-10
     || maximumProjectedError > 1.0e-12
     || maximumRelaxedError > 1.0e-12
    )
    {
        std::cerr << "GATE3D_FAIL role=continuum reason=conservation"
                  << " raw=" << maximumRawError
                  << " projected=" << maximumProjectedError
                  << " relaxed=" << maximumRelaxedError << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << std::setprecision(17)
              << "GATE3D_PASS role=continuum mode=" << mode
              << " two_way_feedback_received=true"
              << " adaptive_interface=true"
              << " activated_layers=" << activatedLayers
              << " deactivated_layers=" << deactivatedLayers
              << " max_raw_conservation_rel=" << maximumRawError
              << " max_projected_conservation_rel=" << maximumProjectedError
              << " max_relaxed_conservation_rel=" << maximumRelaxedError
              << " last_window=" << state.lastWindow
              << " restart=" << outputState
              << " feedback_csv=" << outputCsv << std::endl;
    return EXIT_SUCCESS;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 8)
    {
        std::cerr
            << "Usage: mui_physical_feedback mpi://domain/interface "
            << "dsmc|continuum continuous|fresh|restart comparison.csv "
            << "input.state|- output.state|- output.csv|-" << std::endl;
        return EXIT_FAILURE;
    }
    try
    {
        const std::string role(argv[2]);
        const std::string mode(argv[3]);
        const std::vector<muiFoam::PhysicalWallSample> samples =
            muiFoam::readGate3CComparison(argv[4]);
        mui::uniface2d interface(argv[1]);
        if (role == "dsmc")
        {
            return runDsmcReplay(interface, mode, samples);
        }
        if (role == "continuum")
        {
            return runContinuum
            (
                interface, mode, argv[5], argv[6], argv[7], samples
            );
        }
        throw std::runtime_error("unknown Gate-3D role");
    }
    catch (const std::exception& error)
    {
        std::cerr << "GATE3D_FAIL reason=" << error.what() << std::endl;
        return EXIT_FAILURE;
    }
}
