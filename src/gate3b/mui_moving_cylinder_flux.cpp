// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

#include "muiFoam/AdaptiveInterface.hpp"
#include "muiFoam/ConservativeFlux.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

const int nComponents = 5;
const int nWindows = 5;
const double span = 1.0e-3;
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

struct Resolution
{
    int sourceFaces;
    int targetFaces;
};

Resolution resolution(const std::string& name)
{
    if (name == "coarse")
    {
        return Resolution{12, 16};
    }
    if (name == "medium")
    {
        return Resolution{18, 24};
    }
    if (name == "fine")
    {
        return Resolution{24, 32};
    }
    throw std::runtime_error("unknown Gate-3B pilot resolution");
}

double pi()
{
    return std::acos(-1.0);
}

double interfaceRadius(const int window)
{
    const double values[nWindows] = {0.018, 0.016, 0.014, 0.016, 0.018};
    return values[window];
}

int requestedLayers(const int window)
{
    const int values[nWindows] = {2, 4, 5, 3, 2};
    return values[window];
}

int activeLayers(const int window)
{
    int layers = requestedLayers(0);
    for (int current = 1; current <= window; ++current)
    {
        layers = muiFoam::limitedInterfaceTransition
        (
            layers,
            requestedLayers(current),
            1,
            6
        ).currentLayers;
    }
    return layers;
}

int sampleCount(const int window)
{
    const int values[nWindows] = {32, 128, 256, 256, 512};
    return values[window];
}

double maximumRse(const int window)
{
    const double values[nWindows] = {0.10, 0.04, 0.03, 0.03, 0.02};
    return values[window];
}

double relaxation(const int window)
{
    const double values[nWindows] = {0.0, 0.25, 0.35, 0.35, 0.50};
    return values[window];
}

mui::point2d interfacePoint
(
    const int window,
    const int face,
    const int faceCount
)
{
    if (window < 0 || window >= nWindows || face < 0 || face >= faceCount)
    {
        throw std::runtime_error("invalid moving-cylinder interface point");
    }
    const double theta = -0.5*pi() + (face + 0.5)*pi()/faceCount;
    const double radius = interfaceRadius(window);
    mui::point2d point;
    point[0] = 0.04 + radius*std::cos(theta);
    point[1] = radius*std::sin(theta);
    return point;
}

mui::point2d metadataPoint()
{
    mui::point2d point;
    point[0] = -1.0;
    point[1] = -1.0;
    return point;
}

muiFoam::ConservativeFlux sourceFlux
(
    const int window,
    const int face,
    const int faceCount
)
{
    const double theta = -0.5*pi() + (face + 0.5)*pi()/faceCount;
    const double area = muiFoam::cylindricalFaceArea
    (
        interfaceRadius(window),
        pi()/faceCount,
        span
    );
    const double density = 6.63e-4*(1.0 + 0.12*std::cos(theta));
    const double normalSpeed = 1450.0*(0.25 + 0.75*std::cos(theta));
    const double pressure = 41.4*(1.0 + 0.35*std::cos(theta));
    const double specificEnergy = 1.8e6 + 0.5*normalSpeed*normalSpeed;

    muiFoam::ConservativeFlux flux = muiFoam::zeroFlux();
    flux[0] = density*normalSpeed*area;
    flux[1] = (density*normalSpeed*normalSpeed + pressure)*area;
    flux[2] = 0.04*flux[1]*std::sin(theta);
    flux[3] = 0.0;
    flux[4] = density*normalSpeed*specificEnergy*area;
    return flux;
}

std::vector<int> selectedWindows(const std::string& mode)
{
    if (mode == "continuous")
    {
        return std::vector<int>{0, 1, 2, 3, 4};
    }
    if (mode == "fresh")
    {
        return std::vector<int>{0, 1, 2};
    }
    if (mode == "restart")
    {
        return std::vector<int>{3, 4};
    }
    throw std::runtime_error("unknown Gate-3B pilot segment mode");
}

bool close(const double actual, const double expected)
{
    const double scale = std::max
    (
        1.0,
        std::max(std::abs(actual), std::abs(expected))
    );
    return std::abs(actual - expected) <= 1.0e-12*scale;
}

void publishWindow
(
    mui::uniface2d& interface,
    const int window,
    const Resolution& mesh
)
{
    std::vector<muiFoam::ConservativeFlux> source(mesh.sourceFaces);
    for (int face = 0; face < mesh.sourceFaces; ++face)
    {
        source[face] = sourceFlux(window, face, mesh.sourceFaces);
        const mui::point2d point = interfacePoint(window, face, mesh.sourceFaces);
        for (int component = 0; component < nComponents; ++component)
        {
            interface.push(fluxNames[component], point, source[face][component]);
        }
    }

    const muiFoam::ConservativeFlux total = muiFoam::totalFlux(source);
    const mui::point2d meta = metadataPoint();
    for (int component = 0; component < nComponents; ++component)
    {
        interface.push(totalNames[component], meta, total[component]);
    }
    interface.push("sampleCount", meta, static_cast<double>(sampleCount(window)));
    interface.push("maximumRse", meta, maximumRse(window));
    interface.push("relaxation", meta, relaxation(window));
    interface.push("activeLayers", meta, static_cast<double>(activeLayers(window)));
    interface.push("interfaceRadius", meta, interfaceRadius(window));
    interface.push("receiverReady", meta, 0.0);
}

muiFoam::ConservativeFlux fetchExactTotals
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

int runProducer
(
    mui::uniface2d& interface,
    const std::string& mode,
    const std::string& resolutionName
)
{
    const Resolution mesh = resolution(resolutionName);
    const std::vector<int> windows = selectedWindows(mode);
    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;
    for (std::size_t wi = 0; wi < windows.size(); ++wi)
    {
        const int window = windows[wi];
        publishWindow(interface, window, mesh);
        interface.commit(window);
        const double ready = interface.fetch
        (
            "receiverReady", metadataPoint(), window, exact, temporal
        );
        if (!close(ready, 1.0))
        {
            std::cerr << "GATE3B_PILOT_FAIL role=dsmc reason=handshake"
                      << " window=" << window << std::endl;
            return EXIT_FAILURE;
        }
    }
    std::cout << "GATE3B_PILOT_PASS role=dsmc mode=" << mode
              << " resolution=" << resolutionName
              << " windows=" << windows.size() << std::endl;
    return EXIT_SUCCESS;
}

int runConsumer
(
    mui::uniface2d& interface,
    const std::string& mode,
    const std::string& inputRestart,
    const std::string& outputRestart,
    const std::string& resolutionName
)
{
    const Resolution mesh = resolution(resolutionName);
    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;
    std::vector<muiFoam::ConservativeFlux> state
    (
        mesh.targetFaces,
        muiFoam::zeroFlux()
    );
    int lastWindow = -1;
    if (mode == "restart")
    {
        const muiFoam::FluxRestart restart =
            muiFoam::readFluxRestart(inputRestart, mesh.targetFaces);
        if (restart.lastWindow != 2)
        {
            throw std::runtime_error("Gate-3B pilot restart must resume after window 2");
        }
        state = restart.faces;
        lastWindow = restart.lastWindow;
    }

    const std::vector<int> windows = selectedWindows(mode);
    double maximumRawError = 0.0;
    double maximumMappedError = 0.0;
    double maximumRelaxedError = 0.0;
    double maximumMovingBoundaryError = 0.0;
    int resolvedWindows = 0;
    int skippedWindows = 0;
    int activatedLayers = 0;
    int deactivatedLayers = 0;
    int previousLayers = activeLayers(windows.front());

    for (std::size_t wi = 0; wi < windows.size(); ++wi)
    {
        const int window = windows[wi];
        interface.push("receiverReady", metadataPoint(), 1.0);
        interface.commit(window);

        const int samples = static_cast<int>(std::lround(interface.fetch
        (
            "sampleCount", metadataPoint(), window, exact, temporal
        )));
        const double rse = interface.fetch
        (
            "maximumRse", metadataPoint(), window, exact, temporal
        );
        const double alpha = interface.fetch
        (
            "relaxation", metadataPoint(), window, exact, temporal
        );
        const int layers = static_cast<int>(std::lround(interface.fetch
        (
            "activeLayers", metadataPoint(), window, exact, temporal
        )));
        const double radius = interface.fetch
        (
            "interfaceRadius", metadataPoint(), window, exact, temporal
        );
        if (window > windows.front())
        {
            const muiFoam::InterfaceTransition transition =
                muiFoam::limitedInterfaceTransition
                (
                    previousLayers,
                    requestedLayers(window),
                    1,
                    6
                );
            if (transition.currentLayers != layers)
            {
                throw std::runtime_error("transported interface layer mismatch");
            }
            activatedLayers += transition.activatedLayers;
            deactivatedLayers += transition.deactivatedLayers;
        }
        previousLayers = layers;

        if (!muiFoam::statisticallyResolved(samples, rse))
        {
            ++skippedWindows;
            std::cout << "GATE3B_PILOT_WINDOW window=" << window
                      << " radius=" << radius
                      << " active_layers=" << layers
                      << " samples=" << samples
                      << " max_rse=" << rse
                      << " statistically_resolved=false relaxation_applied=false"
                      << std::endl;
            continue;
        }

        std::vector<mui::point2d> targetPoints;
        std::vector<double> targetAreas;
        for (int face = 0; face < mesh.targetFaces; ++face)
        {
            targetPoints.push_back(interfacePoint(window, face, mesh.targetFaces));
            targetAreas.push_back(muiFoam::cylindricalFaceArea
            (
                radius,
                pi()/mesh.targetFaces,
                span
            ));
        }
        mui::sampler_rbf2d<double> conservativeRbf
        (
            0.10,
            targetPoints,
            0,
            true,
            false,
            true,
            std::string(),
            1.0e-12,
            1.0e-12,
            4000,
            0,
            1
        );

        std::vector<muiFoam::ConservativeFlux> mapped
        (
            mesh.targetFaces,
            muiFoam::zeroFlux()
        );
        for (int face = 0; face < mesh.targetFaces; ++face)
        {
            for (int component = 0; component < nComponents; ++component)
            {
                mapped[face][component] = interface.fetch
                (
                    fluxNames[component],
                    targetPoints[face],
                    window,
                    conservativeRbf,
                    temporal
                );
            }
            if (!muiFoam::finiteFlux(mapped[face]))
            {
                throw std::runtime_error("non-finite moving-cylinder RBF flux");
            }
        }

        const muiFoam::ConservativeFlux sourceTotal =
            fetchExactTotals(interface, window, exact, temporal);
        const double rawError = muiFoam::projectGlobalConservation
        (
            mapped,
            sourceTotal,
            targetAreas
        );
        const double mappedError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(mapped),
            sourceTotal
        );
        const muiFoam::ConservativeFlux previousTotal =
            muiFoam::totalFlux(state);
        for (int face = 0; face < mesh.targetFaces; ++face)
        {
            state[face] = muiFoam::relaxedFlux
            (
                state[face], mapped[face], alpha
            );
        }
        const muiFoam::ConservativeFlux expectedTotal =
            muiFoam::relaxedFlux(previousTotal, sourceTotal, alpha);
        const double relaxedError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(state),
            expectedTotal
        );

        muiFoam::MovingBoundaryBalance balance;
        balance.initial = previousTotal;
        balance.boundaryExchange = muiFoam::zeroFlux();
        balance.sweptInterfaceExchange = muiFoam::zeroFlux();
        for (int component = 0; component < nComponents; ++component)
        {
            balance.boundaryExchange[component] =
                alpha*(sourceTotal[component] - previousTotal[component]);
        }
        balance.final = muiFoam::totalFlux(state);
        const double movingBoundaryError =
            muiFoam::movingBoundaryConservationError(balance);

        maximumRawError = std::max(maximumRawError, rawError);
        maximumMappedError = std::max(maximumMappedError, mappedError);
        maximumRelaxedError = std::max(maximumRelaxedError, relaxedError);
        maximumMovingBoundaryError = std::max
        (
            maximumMovingBoundaryError,
            movingBoundaryError
        );
        ++resolvedWindows;
        lastWindow = window;

        std::cout << std::setprecision(17)
                  << "GATE3B_PILOT_WINDOW window=" << window
                  << " radius=" << radius
                  << " active_layers=" << layers
                  << " samples=" << samples
                  << " max_rse=" << rse
                  << " statistically_resolved=true relaxation_applied=true"
                  << " alpha=" << alpha
                  << " raw_rbf_conservation_rel=" << rawError
                  << " mapped_conservation_rel=" << mappedError
                  << " relaxed_conservation_rel=" << relaxedError
                  << " moving_boundary_conservation_rel="
                  << movingBoundaryError
                  << std::endl;
    }

    if (lastWindow < 0 || outputRestart == "-")
    {
        throw std::runtime_error("no resolved moving-cylinder state to checkpoint");
    }
    muiFoam::writeFluxRestart(outputRestart, lastWindow, state);

    const double rawTolerance = 2.0e-1;
    const double conservationTolerance = 1.0e-8;
    if (maximumRawError > rawTolerance)
    {
        std::cerr << "GATE3B_PILOT_FAIL role=continuum reason=raw_rbf_defect"
                  << " value=" << maximumRawError
                  << " limit=" << rawTolerance << std::endl;
        return EXIT_FAILURE;
    }
    if (maximumMappedError > conservationTolerance
     || maximumRelaxedError > conservationTolerance
     || maximumMovingBoundaryError > conservationTolerance)
    {
        std::cerr << "GATE3B_PILOT_FAIL role=continuum reason=conservation"
                  << " mapped=" << maximumMappedError
                  << " relaxed=" << maximumRelaxedError
                  << " moving=" << maximumMovingBoundaryError
                  << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << std::setprecision(17)
              << "GATE3B_PILOT_PASS role=continuum mode=" << mode
              << " resolution=" << resolutionName
              << " source_faces=" << mesh.sourceFaces
              << " target_faces=" << mesh.targetFaces
              << " resolved_windows=" << resolvedWindows
              << " skipped_windows=" << skippedWindows
              << " activated_layers=" << activatedLayers
              << " deactivated_layers=" << deactivatedLayers
              << " max_raw_rbf_conservation_rel=" << maximumRawError
              << " max_mapped_conservation_rel=" << maximumMappedError
              << " max_relaxed_conservation_rel=" << maximumRelaxedError
              << " max_moving_boundary_conservation_rel="
              << maximumMovingBoundaryError
              << " last_window=" << lastWindow
              << " restart=" << outputRestart
              << std::endl;
    return EXIT_SUCCESS;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 7)
    {
        std::cerr
            << "Usage: mui_moving_cylinder_flux mpi://domain/interface "
            << "dsmc|continuum continuous|fresh|restart "
            << "input.state|- output.state|- coarse|medium|fine"
            << std::endl;
        return EXIT_FAILURE;
    }

    try
    {
        const std::string role(argv[2]);
        const std::string mode(argv[3]);
        const std::string resolutionName(argv[6]);
        mui::uniface2d interface(argv[1]);
        if (role == "dsmc")
        {
            return runProducer(interface, mode, resolutionName);
        }
        if (role == "continuum")
        {
            return runConsumer
            (
                interface,
                mode,
                argv[4],
                argv[5],
                resolutionName
            );
        }
        throw std::runtime_error("unknown Gate-3B pilot role");
    }
    catch (const std::exception& error)
    {
        std::cerr << "GATE3B_PILOT_FAIL reason=" << error.what() << std::endl;
        return EXIT_FAILURE;
    }
}
