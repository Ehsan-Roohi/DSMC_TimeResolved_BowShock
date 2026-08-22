#ifndef Gate1BMui_H
#define Gate1BMui_H

#include "mui.h"

#include <algorithm>
#include <cmath>
#include <string>

namespace gate1b
{

struct State
{
    double rho;
    double ux;
    double uy;
    double uz;
    double temperature;
    double specificEnergy;

    bool physical() const
    {
        return std::isfinite(rho)
            && std::isfinite(ux)
            && std::isfinite(uy)
            && std::isfinite(uz)
            && std::isfinite(temperature)
            && std::isfinite(specificEnergy)
            && rho > 0.0
            && temperature > 0.0
            && specificEnergy > 0.0;
    }
};

inline mui::point3d auditPoint()
{
    mui::point3d point;
    point[0] = 0.0;
    point[1] = 0.0;
    point[2] = 0.0;
    return point;
}

inline std::string key(const std::string& prefix, const char* field)
{
    return prefix + field;
}

inline void pushState
(
    mui::uniface3d& interface,
    const std::string& prefix,
    const State& state
)
{
    const mui::point3d point = auditPoint();
    interface.push(key(prefix, "rho"), point, state.rho);
    interface.push(key(prefix, "Ux"), point, state.ux);
    interface.push(key(prefix, "Uy"), point, state.uy);
    interface.push(key(prefix, "Uz"), point, state.uz);
    interface.push(key(prefix, "T"), point, state.temperature);
    interface.push(key(prefix, "specificEnergy"), point, state.specificEnergy);
}

inline State fetchState
(
    mui::uniface3d& interface,
    const std::string& prefix,
    const int couplingStep
)
{
    mui::sampler_exact3d<double> spatialSampler;
    mui::temporal_sampler_exact3d temporalSampler;
    const mui::point3d point = auditPoint();

    State state;
    state.rho = interface.fetch
    (
        key(prefix, "rho"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.ux = interface.fetch
    (
        key(prefix, "Ux"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.uy = interface.fetch
    (
        key(prefix, "Uy"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.uz = interface.fetch
    (
        key(prefix, "Uz"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.temperature = interface.fetch
    (
        key(prefix, "T"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    state.specificEnergy = interface.fetch
    (
        key(prefix, "specificEnergy"), point, couplingStep,
        spatialSampler, temporalSampler
    );
    return state;
}

inline double relativeStateError(const State& a, const State& b)
{
    const double rhoError = std::abs(a.rho - b.rho)/std::max(a.rho, b.rho);
    const double temperatureError =
        std::abs(a.temperature - b.temperature)
       /std::max(a.temperature, b.temperature);
    const double energyError =
        std::abs(a.specificEnergy - b.specificEnergy)
       /std::max(a.specificEnergy, b.specificEnergy);

    const double dux = a.ux - b.ux;
    const double duy = a.uy - b.uy;
    const double duz = a.uz - b.uz;
    const double velocityScale = std::max
    (
        1.0,
        std::sqrt
        (
            a.ux*a.ux + a.uy*a.uy + a.uz*a.uz
          + b.ux*b.ux + b.uy*b.uy + b.uz*b.uz
        )
    );
    const double velocityError =
        std::sqrt(dux*dux + duy*duy + duz*duz)/velocityScale;

    return std::max
    (
        std::max(rhoError, temperatureError),
        std::max(energyError, velocityError)
    );
}

} // namespace gate1b

#endif
