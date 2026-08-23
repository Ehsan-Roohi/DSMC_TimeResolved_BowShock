// SPDX-License-Identifier: GPL-3.0-or-later
#include "mui.h"

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

const int nSourceFaces = 9;
const int nTargetFaces = 16;
const int nComponents = 5;
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

mui::point2d sourcePoint(const int face)
{
    mui::point2d point;
    const int i = face % 3;
    const int j = face / 3;
    point[0] = (i + 0.5)/3.0;
    point[1] = (j + 0.5)/3.0;
    return point;
}

mui::point2d targetPoint(const int face)
{
    mui::point2d point;
    const int i = face % 4;
    const int j = face / 4;
    point[0] = (i + 0.5)/4.0;
    point[1] = (j + 0.5)/4.0;
    return point;
}

mui::point2d metadataPoint()
{
    mui::point2d point;
    point[0] = -1.0;
    point[1] = -1.0;
    return point;
}

muiFoam::ConservativeFlux sourceFlux(const int window, const int face)
{
    const int i = face % 3;
    const int j = face / 3;
    muiFoam::ConservativeFlux flux = muiFoam::zeroFlux();
    flux[0] = 1.0 + 0.04*face + 0.03*window;
    flux[1] = 5.0 + 0.15*face + 0.10*window;
    flux[2] = -0.20 + 0.06*i + 0.02*window;
    flux[3] = -0.10 + 0.05*j - 0.01*window;
    flux[4] = 20.0 + 0.45*face + 0.30*window;
    return flux;
}

int sampleCount(const int window)
{
    const int counts[3] = {32, 256, 512};
    return counts[window];
}

double maximumRse(const int window)
{
    const double values[3] = {0.10, 0.03, 0.02};
    return values[window];
}

double relaxation(const int window)
{
    const double values[3] = {0.0, 0.35, 0.50};
    return values[window];
}

std::vector<int> selectedWindows(const std::string& mode)
{
    if (mode == "continuous")
    {
        return std::vector<int>{0, 1, 2};
    }
    if (mode == "fresh")
    {
        return std::vector<int>{0, 1};
    }
    if (mode == "restart")
    {
        return std::vector<int>{2};
    }
    throw std::runtime_error("unknown Gate-3A segment mode");
}

bool close(const double a, const double b)
{
    const double scale = std::max(1.0, std::max(std::abs(a), std::abs(b)));
    return std::abs(a - b) <= 1.0e-12*scale;
}

void publishWindow(mui::uniface2d& interface, const int window)
{
    std::vector<muiFoam::ConservativeFlux> source(nSourceFaces);
    for (int face = 0; face < nSourceFaces; ++face)
    {
        source[face] = sourceFlux(window, face);
        const mui::point2d point = sourcePoint(face);
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
    const std::string& mode
)
{
    const std::vector<int> windows = selectedWindows(mode);
    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;
    for (std::size_t wi = 0; wi < windows.size(); ++wi)
    {
        const int window = windows[wi];
        publishWindow(interface, window);
        interface.commit(window);
        const double ready = interface.fetch
        (
            "receiverReady", metadataPoint(), window, exact, temporal
        );
        if (!close(ready, 1.0))
        {
            std::cerr << "GATE3A_FAIL role=dsmc reason=handshake window="
                      << window << std::endl;
            return EXIT_FAILURE;
        }
    }
    std::cout << "GATE3A_PASS role=dsmc mode=" << mode
              << " windows=" << windows.size() << std::endl;
    return EXIT_SUCCESS;
}

int runConsumer
(
    mui::uniface2d& interface,
    const std::string& mode,
    const std::string& inputRestart,
    const std::string& outputRestart
)
{
    std::vector<mui::point2d> targetPoints;
    std::vector<double> targetFaceAreas;
    for (int face = 0; face < nTargetFaces; ++face)
    {
        targetPoints.push_back(targetPoint(face));
        targetFaceAreas.push_back(1.0/static_cast<double>(nTargetFaces));
    }
    mui::sampler_rbf2d<double> conservativeRbf
    (
        2.0,
        targetPoints,
        0,
        true,
        false,
        true,
        std::string(),
        1.0e-12,
        1.0e-12,
        2000,
        0,
        1
    );
    mui::sampler_exact2d<double> exact;
    mui::temporal_sampler_exact2d temporal;

    std::vector<muiFoam::ConservativeFlux> state
    (
        nTargetFaces,
        muiFoam::zeroFlux()
    );
    int lastWindow = -1;
    if (mode == "restart")
    {
        const muiFoam::FluxRestart restart =
            muiFoam::readFluxRestart(inputRestart, nTargetFaces);
        if (restart.lastWindow != 1)
        {
            throw std::runtime_error("Gate-3A restart must resume after window 1");
        }
        state = restart.faces;
        lastWindow = restart.lastWindow;
    }

    const std::vector<int> windows = selectedWindows(mode);
    double maximumRawRbfConservationError = 0.0;
    double maximumMappedConservationError = 0.0;
    double maximumRelaxedConservationError = 0.0;
    int resolvedWindows = 0;
    int skippedWindows = 0;

    for (std::size_t wi = 0; wi < windows.size(); ++wi)
    {
        const int window = windows[wi];
        interface.push("receiverReady", metadataPoint(), 1.0);
        interface.commit(window);

        const int samples = static_cast<int>
        (
            std::lround
            (
                interface.fetch
                (
                    "sampleCount", metadataPoint(), window, exact, temporal
                )
            )
        );
        const double rse = interface.fetch
        (
            "maximumRse", metadataPoint(), window, exact, temporal
        );
        const double alpha = interface.fetch
        (
            "relaxation", metadataPoint(), window, exact, temporal
        );

        if (!muiFoam::statisticallyResolved(samples, rse))
        {
            ++skippedWindows;
            std::cout << "GATE3A_WINDOW window=" << window
                      << " samples=" << samples
                      << " max_rse=" << rse
                      << " statistically_resolved=false relaxation_applied=false"
                      << std::endl;
            continue;
        }

        std::vector<muiFoam::ConservativeFlux> mapped
        (
            nTargetFaces,
            muiFoam::zeroFlux()
        );
        for (int face = 0; face < nTargetFaces; ++face)
        {
            for (int component = 0; component < nComponents; ++component)
            {
                mapped[face][component] = interface.fetch
                (
                    fluxNames[component],
                    targetPoint(face),
                    window,
                    conservativeRbf,
                    temporal
                );
            }
            if (!muiFoam::finiteFlux(mapped[face]))
            {
                throw std::runtime_error("non-finite RBF-mapped flux");
            }
        }

        const muiFoam::ConservativeFlux sourceTotal =
            fetchExactTotals(interface, window, exact, temporal);
        const double rawRbfError = muiFoam::projectGlobalConservation
        (
            mapped,
            sourceTotal,
            targetFaceAreas
        );
        maximumRawRbfConservationError = std::max
        (
            maximumRawRbfConservationError,
            rawRbfError
        );
        const muiFoam::ConservativeFlux mappedTotal =
            muiFoam::totalFlux(mapped);
        const double mappedError = muiFoam::maximumRelativeDifference
        (
            mappedTotal,
            sourceTotal
        );
        maximumMappedConservationError = std::max
        (
            maximumMappedConservationError,
            mappedError
        );

        const muiFoam::ConservativeFlux previousTotal =
            muiFoam::totalFlux(state);
        for (int face = 0; face < nTargetFaces; ++face)
        {
            state[face] = muiFoam::relaxedFlux(state[face], mapped[face], alpha);
        }
        const muiFoam::ConservativeFlux expectedRelaxedTotal =
            muiFoam::relaxedFlux(previousTotal, sourceTotal, alpha);
        const double relaxedError = muiFoam::maximumRelativeDifference
        (
            muiFoam::totalFlux(state),
            expectedRelaxedTotal
        );
        maximumRelaxedConservationError = std::max
        (
            maximumRelaxedConservationError,
            relaxedError
        );
        ++resolvedWindows;
        lastWindow = window;
        std::cout << std::setprecision(17)
                  << "GATE3A_WINDOW window=" << window
                  << " samples=" << samples
                  << " max_rse=" << rse
                  << " statistically_resolved=true relaxation_applied=true"
                  << " alpha=" << alpha
                  << " raw_rbf_conservation_rel=" << rawRbfError
                  << " mapped_conservation_rel=" << mappedError
                  << " relaxed_conservation_rel=" << relaxedError
                  << std::endl;
    }

    if (lastWindow < 0 || outputRestart == "-")
    {
        throw std::runtime_error("no resolved flux state to checkpoint");
    }
    muiFoam::writeFluxRestart(outputRestart, lastWindow, state);

    const double rawRbfTolerance = 5.0e-2;
    const double tolerance = 1.0e-8;
    if (maximumRawRbfConservationError > rawRbfTolerance)
    {
        std::cerr << "GATE3A_FAIL role=continuum reason=raw_rbf_defect"
                  << " raw_rbf=" << maximumRawRbfConservationError
                  << " limit=" << rawRbfTolerance
                  << std::endl;
        return EXIT_FAILURE;
    }
    if (maximumMappedConservationError > tolerance
     || maximumRelaxedConservationError > tolerance)
    {
        std::cerr << "GATE3A_FAIL role=continuum reason=conservation"
                  << " mapped=" << maximumMappedConservationError
                  << " relaxed=" << maximumRelaxedConservationError
                  << std::endl;
        return EXIT_FAILURE;
    }

    std::cout << std::setprecision(17)
              << "GATE3A_PASS role=continuum mode=" << mode
              << " resolved_windows=" << resolvedWindows
              << " skipped_windows=" << skippedWindows
              << " max_raw_rbf_conservation_rel="
              << maximumRawRbfConservationError
              << " max_mapped_conservation_rel="
              << maximumMappedConservationError
              << " max_relaxed_conservation_rel="
              << maximumRelaxedConservationError
              << " last_window=" << lastWindow
              << " restart=" << outputRestart
              << std::endl;
    return EXIT_SUCCESS;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc != 6)
    {
        std::cerr
            << "Usage: mui_conservative_flux mpi://domain/interface "
            << "dsmc|continuum continuous|fresh|restart input.state|- output.state|-"
            << std::endl;
        return EXIT_FAILURE;
    }

    try
    {
        const std::string role(argv[2]);
        const std::string mode(argv[3]);
        mui::uniface2d interface(argv[1]);
        if (role == "dsmc")
        {
            return runProducer(interface, mode);
        }
        if (role == "continuum")
        {
            return runConsumer(interface, mode, argv[4], argv[5]);
        }
        throw std::runtime_error("unknown Gate-3A role");
    }
    catch (const std::exception& error)
    {
        std::cerr << "GATE3A_FAIL reason=" << error.what() << std::endl;
        return EXIT_FAILURE;
    }
}
