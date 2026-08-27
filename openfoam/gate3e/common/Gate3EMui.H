#ifndef Gate3EMui_H
#define Gate3EMui_H

#include "Gate3CMui.H"

#include <algorithm>
#include <cmath>

namespace gate3e
{

constexpr int couplingWindows = 5;
constexpr int windowSteps = 200;
constexpr int kineticSteps = couplingWindows*windowSteps;
constexpr int sampleStride = 5;
constexpr int samplesPerWindow = windowSteps/sampleStride;
constexpr double maximumFractionalCorrection = 0.01;

struct Feedback
{
    double mass;
    double momentumX;
    double momentumY;
    double momentumZ;
    double energy;
    int samples;

    bool physical() const
    {
        return std::isfinite(mass)
            && std::isfinite(momentumX)
            && std::isfinite(momentumY)
            && std::isfinite(momentumZ)
            && std::isfinite(energy)
            && samples == samplesPerWindow
            && std::abs(mass) <= 1.0e-30;
    }
};

inline mui::point3d continuumSamplePoint
(
    const int pointIndex,
    const int activeLayers
)
{
    const int boundedLayers = std::max(4, std::min(8, activeLayers));
    const double theta = gate3c::centreAngle(pointIndex);
    const double radius = gate3c::cylinderRadius
        + (boundedLayers + 0.5)*gate3c::continuumRadialWidth;
    return gate3c::makePoint
    (
        radius*std::cos(theta),
        radius*std::sin(theta),
        0.0
    );
}

inline void pushActiveLayers
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const int activeLayers
)
{
    interface.push("activeLayers", point, static_cast<double>(activeLayers));
}

inline int fetchActiveLayers
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const int couplingStep
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    const double value = interface.fetch
    (
        "activeLayers", point, couplingStep,
        spatialSampler, temporalSampler
    );
    const int layers = static_cast<int>(std::lround(value));
    return std::abs(value - layers) <= 1.0e-12 ? layers : -1;
}

inline void pushFeedback
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const Feedback& feedback
)
{
    interface.push("feedback_mass", point, feedback.mass);
    interface.push("feedback_momentum_x", point, feedback.momentumX);
    interface.push("feedback_momentum_y", point, feedback.momentumY);
    interface.push("feedback_momentum_z", point, feedback.momentumZ);
    interface.push("feedback_energy", point, feedback.energy);
    interface.push
    (
        "feedback_samples", point, static_cast<double>(feedback.samples)
    );
}

inline Feedback fetchFeedback
(
    mui::uniface3d& interface,
    const mui::point3d& point,
    const int couplingStep
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    Feedback feedback;
    feedback.mass = interface.fetch
    (
        "feedback_mass", point, couplingStep,
        spatialSampler, temporalSampler
    );
    feedback.momentumX = interface.fetch
    (
        "feedback_momentum_x", point, couplingStep,
        spatialSampler, temporalSampler
    );
    feedback.momentumY = interface.fetch
    (
        "feedback_momentum_y", point, couplingStep,
        spatialSampler, temporalSampler
    );
    feedback.momentumZ = interface.fetch
    (
        "feedback_momentum_z", point, couplingStep,
        spatialSampler, temporalSampler
    );
    feedback.energy = interface.fetch
    (
        "feedback_energy", point, couplingStep,
        spatialSampler, temporalSampler
    );
    feedback.samples = static_cast<int>(std::lround(interface.fetch
    (
        "feedback_samples", point, couplingStep,
        spatialSampler, temporalSampler
    )));
    return feedback;
}

} // namespace gate3e

#endif
