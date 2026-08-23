// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_CONSERVATIVE_FLUX_HPP
#define MUIFOAM_CONSERVATIVE_FLUX_HPP

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace muiFoam
{

using ConservativeFlux = std::array<double, 5>;

struct FluxRestart
{
    int lastWindow;
    std::vector<ConservativeFlux> faces;
};

inline bool finiteFlux(const ConservativeFlux& flux)
{
    for (std::size_t i = 0; i < flux.size(); ++i)
    {
        if (!std::isfinite(flux[i]))
        {
            return false;
        }
    }
    return true;
}

inline ConservativeFlux zeroFlux()
{
    ConservativeFlux flux = {{0.0, 0.0, 0.0, 0.0, 0.0}};
    return flux;
}

inline ConservativeFlux totalFlux
(
    const std::vector<ConservativeFlux>& faceFluxes
)
{
    ConservativeFlux total = zeroFlux();
    for (std::size_t face = 0; face < faceFluxes.size(); ++face)
    {
        if (!finiteFlux(faceFluxes[face]))
        {
            throw std::runtime_error("non-finite conservative flux");
        }
        for (std::size_t component = 0; component < total.size(); ++component)
        {
            total[component] += faceFluxes[face][component];
        }
    }
    return total;
}

inline ConservativeFlux relaxedFlux
(
    const ConservativeFlux& previous,
    const ConservativeFlux& current,
    const double alpha
)
{
    if (!finiteFlux(previous) || !finiteFlux(current)
     || !std::isfinite(alpha) || alpha < 0.0 || alpha > 1.0)
    {
        throw std::runtime_error("invalid flux relaxation input");
    }
    ConservativeFlux result = zeroFlux();
    for (std::size_t component = 0; component < result.size(); ++component)
    {
        result[component] =
            (1.0 - alpha)*previous[component] + alpha*current[component];
    }
    return result;
}

inline double maximumRelativeDifference
(
    const ConservativeFlux& actual,
    const ConservativeFlux& expected
)
{
    double maximum = 0.0;
    for (std::size_t component = 0; component < actual.size(); ++component)
    {
        const double scale = std::max
        (
            1.0,
            std::max(std::abs(actual[component]), std::abs(expected[component]))
        );
        maximum = std::max
        (
            maximum,
            std::abs(actual[component] - expected[component])/scale
        );
    }
    return maximum;
}

inline double projectGlobalConservation
(
    std::vector<ConservativeFlux>& faceFluxes,
    const ConservativeFlux& expectedTotal,
    const std::vector<double>& faceAreas
)
{
    if (faceFluxes.empty() || faceFluxes.size() != faceAreas.size()
     || !finiteFlux(expectedTotal))
    {
        throw std::runtime_error("invalid global conservation projection input");
    }

    double totalArea = 0.0;
    std::size_t closureFace = 0;
    for (std::size_t face = 0; face < faceAreas.size(); ++face)
    {
        if (!std::isfinite(faceAreas[face]) || faceAreas[face] <= 0.0)
        {
            throw std::runtime_error("invalid target face area");
        }
        if (faceAreas[face] > faceAreas[closureFace])
        {
            closureFace = face;
        }
        totalArea += faceAreas[face];
    }
    if (!std::isfinite(totalArea) || totalArea <= 0.0)
    {
        throw std::runtime_error("invalid total target area");
    }

    const ConservativeFlux before = totalFlux(faceFluxes);
    const double rawError = maximumRelativeDifference(before, expectedTotal);
    ConservativeFlux residual = zeroFlux();
    for (std::size_t component = 0; component < residual.size(); ++component)
    {
        residual[component] = expectedTotal[component] - before[component];
    }

    // Remove only the global constant-mode defect left by the RBF operator.
    // Integrated flux is distributed in proportion to continuum face area.
    for (std::size_t face = 0; face < faceFluxes.size(); ++face)
    {
        const double fraction = faceAreas[face]/totalArea;
        for (std::size_t component = 0;
             component < faceFluxes[face].size(); ++component)
        {
            faceFluxes[face][component] += fraction*residual[component];
        }
    }

    // Close the final floating-point summation residual on one valid face.
    const ConservativeFlux projectedTotal = totalFlux(faceFluxes);
    for (std::size_t component = 0;
         component < faceFluxes[closureFace].size(); ++component)
    {
        faceFluxes[closureFace][component] +=
            expectedTotal[component] - projectedTotal[component];
    }
    if (!finiteFlux(faceFluxes[closureFace]))
    {
        throw std::runtime_error("non-finite projected conservative flux");
    }
    return rawError;
}

inline bool statisticallyResolved
(
    const int samples,
    const double maximumRelativeStandardError,
    const int minimumSamples = 64,
    const double maximumAllowedRelativeStandardError = 0.05
)
{
    return samples >= minimumSamples
        && std::isfinite(maximumRelativeStandardError)
        && maximumRelativeStandardError >= 0.0
        && maximumRelativeStandardError <= maximumAllowedRelativeStandardError;
}

inline void writeFluxRestart
(
    const std::string& path,
    const int lastWindow,
    const std::vector<ConservativeFlux>& faces
)
{
    if (lastWindow < 0 || faces.empty())
    {
        throw std::runtime_error("invalid restart state");
    }
    for (std::size_t face = 0; face < faces.size(); ++face)
    {
        if (!finiteFlux(faces[face]))
        {
            throw std::runtime_error("non-finite restart state");
        }
    }

    const std::string temporary = path + ".tmp";
    std::ofstream output(temporary.c_str(), std::ios::out | std::ios::trunc);
    if (!output)
    {
        throw std::runtime_error("cannot create restart file");
    }
    output << "GATE3A_RESTART_V1\n"
           << "last_window " << lastWindow << '\n'
           << "faces " << faces.size() << '\n'
           << std::scientific << std::setprecision(17);
    for (std::size_t face = 0; face < faces.size(); ++face)
    {
        for (std::size_t component = 0; component < faces[face].size(); ++component)
        {
            if (component != 0)
            {
                output << ' ';
            }
            output << faces[face][component];
        }
        output << '\n';
    }
    output.close();
    if (!output || std::rename(temporary.c_str(), path.c_str()) != 0)
    {
        std::remove(temporary.c_str());
        throw std::runtime_error("cannot commit restart file");
    }
}

inline FluxRestart readFluxRestart
(
    const std::string& path,
    const std::size_t expectedFaces
)
{
    std::ifstream input(path.c_str());
    std::string magic;
    std::string key;
    FluxRestart restart;
    std::size_t faceCount = 0;
    if (!input || !(input >> magic) || magic != "GATE3A_RESTART_V1"
     || !(input >> key >> restart.lastWindow) || key != "last_window"
     || !(input >> key >> faceCount) || key != "faces"
     || restart.lastWindow < 0 || faceCount != expectedFaces)
    {
        throw std::runtime_error("invalid restart header");
    }

    restart.faces.assign(faceCount, zeroFlux());
    for (std::size_t face = 0; face < faceCount; ++face)
    {
        for (std::size_t component = 0; component < restart.faces[face].size(); ++component)
        {
            if (!(input >> restart.faces[face][component]))
            {
                throw std::runtime_error("truncated restart data");
            }
        }
        if (!finiteFlux(restart.faces[face]))
        {
            throw std::runtime_error("non-finite restart data");
        }
    }
    std::string trailing;
    if (input >> trailing)
    {
        throw std::runtime_error("trailing restart data");
    }
    return restart;
}

} // namespace muiFoam

#endif
