// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_PHYSICAL_FEEDBACK_HPP
#define MUIFOAM_PHYSICAL_FEEDBACK_HPP

#include "muiFoam/AdaptiveInterface.hpp"
#include "muiFoam/ConservativeFlux.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace muiFoam
{

struct PhysicalWallSample
{
    int face;
    double theta;
    double area;
    double referenceHeatFlux;
    double referenceHeatFluxCi95;
    double hybridHeatFlux;
    double referenceDragDensity;
    double referenceDragCi95;
    double hybridDragDensity;
};

struct PhysicalFeedbackState
{
    int lastWindow;
    std::vector<int> activeLayers;
    std::vector<ConservativeFlux> faces;
};

inline std::vector<std::string> splitCsv(const std::string& line)
{
    std::vector<std::string> fields;
    std::stringstream stream(line);
    std::string field;
    while (std::getline(stream, field, ','))
    {
        fields.push_back(field);
    }
    return fields;
}

inline void stripCsvCarriageReturn(std::string& line)
{
    if (!line.empty() && line.back() == '\r')
    {
        line.pop_back();
    }
}

inline std::vector<PhysicalWallSample> readGate3CComparison
(
    const std::string& path,
    const std::size_t expectedFaces = 64
)
{
    std::ifstream input(path.c_str());
    std::string line;
    const std::string header =
        "face,theta,area,reference_q,reference_q_ci95,hybrid_q,"
        "reference_drag_density,reference_drag_ci95,hybrid_drag_density";
    if (!input || !std::getline(input, line))
    {
        throw std::runtime_error("invalid Gate-3C comparison header");
    }
    stripCsvCarriageReturn(line);
    if (line != header)
    {
        throw std::runtime_error("invalid Gate-3C comparison header");
    }

    std::vector<PhysicalWallSample> samples;
    while (std::getline(input, line))
    {
        stripCsvCarriageReturn(line);
        if (line.empty())
        {
            continue;
        }
        const std::vector<std::string> field = splitCsv(line);
        if (field.size() != 9)
        {
            throw std::runtime_error("invalid Gate-3C comparison row");
        }
        PhysicalWallSample sample;
        sample.face = std::stoi(field[0]);
        sample.theta = std::stod(field[1]);
        sample.area = std::stod(field[2]);
        sample.referenceHeatFlux = std::stod(field[3]);
        sample.referenceHeatFluxCi95 = std::stod(field[4]);
        sample.hybridHeatFlux = std::stod(field[5]);
        sample.referenceDragDensity = std::stod(field[6]);
        sample.referenceDragCi95 = std::stod(field[7]);
        sample.hybridDragDensity = std::stod(field[8]);
        const double values[] =
        {
            sample.theta,
            sample.area,
            sample.referenceHeatFlux,
            sample.referenceHeatFluxCi95,
            sample.hybridHeatFlux,
            sample.referenceDragDensity,
            sample.referenceDragCi95,
            sample.hybridDragDensity
        };
        if
        (
            sample.face != static_cast<int>(samples.size())
         || sample.area <= 0.0
         || sample.referenceHeatFluxCi95 < 0.0
         || sample.referenceDragCi95 < 0.0
         || !std::all_of
            (
                values,
                values + sizeof(values)/sizeof(values[0]),
                [](const double value) { return std::isfinite(value); }
            )
        )
        {
            throw std::runtime_error("nonphysical Gate-3C comparison row");
        }
        samples.push_back(sample);
    }
    if (samples.size() != expectedFaces)
    {
        throw std::runtime_error("incomplete Gate-3C wall-face inventory");
    }
    return samples;
}

inline double robustScale
(
    const std::vector<PhysicalWallSample>& samples,
    const bool heatFlux
)
{
    double squared = 0.0;
    for (std::size_t face = 0; face < samples.size(); ++face)
    {
        const double value = heatFlux
            ? samples[face].referenceHeatFlux
            : samples[face].referenceDragDensity;
        squared += value*value;
    }
    return std::max(std::sqrt(squared/std::max<std::size_t>(1, samples.size())), 1.0e-300);
}

inline double physicalDiscrepancyIndicator
(
    const PhysicalWallSample& sample,
    const double heatFluxScale,
    const double dragScale
)
{
    const double heatDenominator = std::max
    (
        std::abs(sample.referenceHeatFlux) + sample.referenceHeatFluxCi95,
        0.05*heatFluxScale
    );
    const double dragDenominator = std::max
    (
        std::abs(sample.referenceDragDensity) + sample.referenceDragCi95,
        0.05*dragScale
    );
    const double heat = std::abs
    (
        sample.hybridHeatFlux - sample.referenceHeatFlux
    )/heatDenominator;
    const double drag = std::abs
    (
        sample.hybridDragDensity - sample.referenceDragDensity
    )/dragDenominator;
    return std::max(heat, drag);
}

inline int requestedPhysicalLayers(const double indicator)
{
    if (!std::isfinite(indicator) || indicator < 0.0)
    {
        throw std::runtime_error("invalid physical discrepancy indicator");
    }
    if (indicator < 0.25) return 4;
    if (indicator < 0.50) return 5;
    if (indicator < 1.00) return 6;
    if (indicator < 2.00) return 7;
    return 8;
}

inline int physicalLayersAtWindow
(
    const double indicator,
    const int window,
    const int initialLayers = 6
)
{
    if (window < 0)
    {
        throw std::runtime_error("negative physical-feedback window");
    }
    int layers = initialLayers;
    const int requested = requestedPhysicalLayers(indicator);
    for (int current = 0; current <= window; ++current)
    {
        layers = limitedInterfaceTransition
        (
            layers, requested, 4, 8, 1
        ).currentLayers;
    }
    return layers;
}

inline ConservativeFlux physicalIntegratedFlux
(
    const PhysicalWallSample& sample,
    const double windowDuration
)
{
    if (!std::isfinite(windowDuration) || windowDuration <= 0.0)
    {
        throw std::runtime_error("invalid physical-feedback duration");
    }
    ConservativeFlux flux = zeroFlux();
    // Gate 3C reports gas-to-wall heat and force density.  Gate 3D transports
    // their integrated reaction packet; the OpenFOAM utility applies the
    // opposite sign to the gas conservative state.
    flux[0] = 0.0;
    flux[1] = sample.hybridDragDensity*sample.area*windowDuration;
    flux[2] = 0.0;
    flux[3] = 0.0;
    flux[4] = sample.hybridHeatFlux*sample.area*windowDuration;
    if (!finiteFlux(flux))
    {
        throw std::runtime_error("non-finite physical feedback packet");
    }
    return flux;
}

inline void writePhysicalFeedbackState
(
    const std::string& path,
    const PhysicalFeedbackState& state
)
{
    if
    (
        state.lastWindow < 0
     || state.faces.empty()
     || state.faces.size() != state.activeLayers.size()
    )
    {
        throw std::runtime_error("invalid physical-feedback restart state");
    }
    const std::string temporary = path + ".tmp";
    std::ofstream output(temporary.c_str(), std::ios::out | std::ios::trunc);
    if (!output)
    {
        throw std::runtime_error("cannot create physical-feedback restart");
    }
    output << "GATE3D_PHYSICAL_FEEDBACK_V1\n"
           << "last_window " << state.lastWindow << '\n'
           << "faces " << state.faces.size() << '\n'
           << std::scientific << std::setprecision(17);
    for (std::size_t face = 0; face < state.faces.size(); ++face)
    {
        if
        (
            state.activeLayers[face] < 4
         || state.activeLayers[face] > 8
         || !finiteFlux(state.faces[face])
        )
        {
            throw std::runtime_error("invalid physical-feedback face state");
        }
        output << state.activeLayers[face];
        for (std::size_t component = 0;
             component < state.faces[face].size(); ++component)
        {
            output << ' ' << state.faces[face][component];
        }
        output << '\n';
    }
    output.close();
    if (!output || std::rename(temporary.c_str(), path.c_str()) != 0)
    {
        std::remove(temporary.c_str());
        throw std::runtime_error("cannot commit physical-feedback restart");
    }
}

inline PhysicalFeedbackState readPhysicalFeedbackState
(
    const std::string& path,
    const std::size_t expectedFaces
)
{
    std::ifstream input(path.c_str());
    std::string magic;
    std::string key;
    std::size_t faceCount = 0;
    PhysicalFeedbackState state;
    if
    (
        !input
     || !(input >> magic) || magic != "GATE3D_PHYSICAL_FEEDBACK_V1"
     || !(input >> key >> state.lastWindow) || key != "last_window"
     || !(input >> key >> faceCount) || key != "faces"
     || state.lastWindow < 0 || faceCount != expectedFaces
    )
    {
        throw std::runtime_error("invalid physical-feedback restart header");
    }
    state.activeLayers.assign(faceCount, 0);
    state.faces.assign(faceCount, zeroFlux());
    for (std::size_t face = 0; face < faceCount; ++face)
    {
        if (!(input >> state.activeLayers[face]))
        {
            throw std::runtime_error("truncated physical-feedback restart");
        }
        for (std::size_t component = 0;
             component < state.faces[face].size(); ++component)
        {
            if (!(input >> state.faces[face][component]))
            {
                throw std::runtime_error("truncated physical-feedback restart");
            }
        }
        if
        (
            state.activeLayers[face] < 4
         || state.activeLayers[face] > 8
         || !finiteFlux(state.faces[face])
        )
        {
            throw std::runtime_error("invalid physical-feedback restart row");
        }
    }
    std::string trailing;
    if (input >> trailing)
    {
        throw std::runtime_error("trailing physical-feedback restart data");
    }
    return state;
}

} // namespace muiFoam

#endif
