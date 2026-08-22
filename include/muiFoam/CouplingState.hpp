// SPDX-License-Identifier: GPL-3.0-or-later
#ifndef MUIFOAM_COUPLING_STATE_HPP
#define MUIFOAM_COUPLING_STATE_HPP

#include <cmath>

namespace muiFoam
{

struct CouplingState
{
    double rho;
    double ux;
    double uy;
    double uz;
    double temperature;

    bool finite() const
    {
        return std::isfinite(rho)
            && std::isfinite(ux)
            && std::isfinite(uy)
            && std::isfinite(uz)
            && std::isfinite(temperature);
    }

    bool physical() const
    {
        return finite() && rho > 0.0 && temperature > 0.0;
    }
};

} // namespace muiFoam

#endif
