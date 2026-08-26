#ifndef Gate3CMui_H
#define Gate3CMui_H

#include "mui.h"

#include <cmath>

namespace gate3c
{

constexpr int angularCells = 64;
constexpr int kineticSteps = 1600;
constexpr int sampleStartStep = 600;
constexpr int sampleStride = 5;
constexpr double pi = 3.141592653589793238462643383279502884;
constexpr double cylinderRadius = 0.01;
constexpr double interfaceRadius = 0.025;
constexpr double outerRadius = 0.05;
constexpr double kineticSpan = 0.0025;
constexpr double angularWidth = 2.0*pi/angularCells;
constexpr double kineticRadialWidth = 0.0025;
constexpr double continuumRadialWidth =
    (outerRadius - cylinderRadius)/32.0;

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

inline double centreAngle(const int pointIndex)
{
    return (pointIndex + 0.5)*angularWidth;
}

inline mui::point3d transportPoint(const int pointIndex)
{
    const double theta = centreAngle(pointIndex);
    return makePoint
    (
        interfaceRadius*std::cos(theta),
        interfaceRadius*std::sin(theta),
        0.0
    );
}

inline mui::point3d continuumSamplePoint(const int pointIndex)
{
    const double theta = centreAngle(pointIndex);
    const double radius = interfaceRadius + 0.5*continuumRadialWidth;
    return makePoint
    (
        radius*std::cos(theta),
        radius*std::sin(theta),
        0.0
    );
}

inline int pointIndex(const double x, const double y)
{
    double theta = std::atan2(y, x);
    if (theta < 0.0)
    {
        theta += 2.0*pi;
    }
    int result = static_cast<int>(std::floor(theta/angularWidth));
    if (result == angularCells)
    {
        result = 0;
    }
    return result >= 0 && result < angularCells ? result : -1;
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
        "numberDensity", point, couplingStep, spatialSampler, temporalSampler
    );
    state.ux = interface.fetch
    (
        "Ux", point, couplingStep, spatialSampler, temporalSampler
    );
    state.uy = interface.fetch
    (
        "Uy", point, couplingStep, spatialSampler, temporalSampler
    );
    state.uz = interface.fetch
    (
        "Uz", point, couplingStep, spatialSampler, temporalSampler
    );
    state.temperature = interface.fetch
    (
        "T", point, couplingStep, spatialSampler, temporalSampler
    );
    return state;
}

inline mui::point3d acknowledgementPoint()
{
    return makePoint(0.0, 0.0, 0.0);
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
        "acknowledgement", acknowledgementPoint(), couplingStep,
        spatialSampler, temporalSampler
    );
}

} // namespace gate3c

#endif
