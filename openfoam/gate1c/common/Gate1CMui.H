#ifndef Gate1CMui_H
#define Gate1CMui_H

#include "mui.h"

#include <cmath>
#include <string>

namespace gate1c
{

constexpr int streamwiseCells = 40;
constexpr int hybridNormalCells = 6;
constexpr int couplingPointCount =
    streamwiseCells + 2*hybridNormalCells;
constexpr int kineticSteps = 1600;
constexpr int sampleStartStep = 600;
constexpr int sampleStride = 5;
constexpr double plateLength = 0.1;
constexpr double interfaceHeight = 0.015;
constexpr double fullHeight = 0.05;
constexpr double kineticDx = plateLength/streamwiseCells;
constexpr double kineticDy = interfaceHeight/hybridNormalCells;
constexpr double continuumDx = plateLength/80.0;
constexpr double continuumDy = fullHeight/40.0;

struct State
{
    double numberDensity;
    double ux;
    double uy;
    double uz;
    double temperature;

    bool physical() const
    {
        return std::isfinite(numberDensity)
            && std::isfinite(ux)
            && std::isfinite(uy)
            && std::isfinite(uz)
            && std::isfinite(temperature)
            && numberDensity > 0.0
            && temperature > 0.0;
    }
};

inline mui::point3d makePoint(const double x, const double y, const double z)
{
    mui::point3d point;
    point[0] = x;
    point[1] = y;
    point[2] = z;
    return point;
}

// Ordering is inlet bottom-to-top, internal top interface left-to-right,
// then outlet bottom-to-top.  Both MUI applications use this immutable list.
inline mui::point3d transportPoint(const int pointIndex)
{
    if (pointIndex < hybridNormalCells)
    {
        return makePoint
        (
            0.0,
            (pointIndex + 0.5)*kineticDy,
            0.0
        );
    }

    const int interfaceEnd = hybridNormalCells + streamwiseCells;
    if (pointIndex < interfaceEnd)
    {
        const int i = pointIndex - hybridNormalCells;
        return makePoint
        (
            (i + 0.5)*kineticDx,
            interfaceHeight,
            0.0
        );
    }

    const int j = pointIndex - interfaceEnd;
    return makePoint
    (
        plateLength,
        (j + 0.5)*kineticDy,
        0.0
    );
}

// Sampling points are half a continuum cell inside the full continuum mesh.
// Their MUI transport locations remain the exact kinetic boundary face centres.
inline mui::point3d continuumSamplePoint(const int pointIndex)
{
    const mui::point3d transport = transportPoint(pointIndex);
    if (pointIndex < hybridNormalCells)
    {
        return makePoint(0.5*continuumDx, transport[1], 0.0);
    }

    const int interfaceEnd = hybridNormalCells + streamwiseCells;
    if (pointIndex < interfaceEnd)
    {
        return makePoint
        (
            transport[0],
            interfaceHeight - 0.5*continuumDy,
            0.0
        );
    }

    return makePoint
    (
        plateLength - 0.5*continuumDx,
        transport[1],
        0.0
    );
}

inline int pointIndex(const double x, const double y)
{
    const double tolerance = 1.0e-10;
    if (std::abs(x) <= tolerance)
    {
        const int j = static_cast<int>(std::floor(y/kineticDy));
        return j >= 0 && j < hybridNormalCells ? j : -1;
    }

    if (std::abs(y - interfaceHeight) <= tolerance)
    {
        const int i = static_cast<int>(std::floor(x/kineticDx));
        return i >= 0 && i < streamwiseCells
            ? hybridNormalCells + i
            : -1;
    }

    if (std::abs(x - plateLength) <= tolerance)
    {
        const int j = static_cast<int>(std::floor(y/kineticDy));
        return j >= 0 && j < hybridNormalCells
            ? hybridNormalCells + streamwiseCells + j
            : -1;
    }

    return -1;
}

inline void pushState
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const State& state
)
{
    interface.push("numberDensity", point, state.numberDensity);
    interface.push("Ux", point, state.ux);
    interface.push("Uy", point, state.uy);
    interface.push("Uz", point, state.uz);
    interface.push("T", point, state.temperature);
}

inline State fetchState
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const int couplingStep
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;

    State state;
    state.numberDensity = interface.fetch
    (
        "numberDensity", point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.ux = interface.fetch
    (
        "Ux", point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.uy = interface.fetch
    (
        "Uy", point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.uz = interface.fetch
    (
        "Uz", point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.temperature = interface.fetch
    (
        "T", point, couplingStep,
        spatialSampler, temporalSampler
    );
    return state;
}

inline mui::point3d acknowledgementPoint()
{
    return makePoint(-1.0, -1.0, -1.0);
}

inline void pushAcknowledgement
(
    mui::uniface3d& interface,
    const int couplingStep
)
{
    interface.push
    (
        "acknowledgement",
        acknowledgementPoint(),
        static_cast<double>(couplingStep)
    );
}

inline double fetchAcknowledgement
(
    mui::uniface3d& interface,
    const int couplingStep
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    return interface.fetch
    (
        "acknowledgement",
        acknowledgementPoint(),
        couplingStep,
        spatialSampler,
        temporalSampler
    );
}

} // namespace gate1c

#endif
