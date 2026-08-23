// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "Gate1CMui.H"

#include <algorithm>
#include <cmath>
#include <vector>

namespace
{

constexpr double boltzmann = 1.380649e-23;

Foam::label nearestCell(const Foam::fvMesh& mesh, const mui::point3d& point)
{
    const Foam::point sample(point[0], point[1], point[2]);
    Foam::label nearest = -1;
    Foam::scalar nearestDistance = Foam::GREAT;
    forAll(mesh.C(), celli)
    {
        const Foam::scalar distance = Foam::magSqr(mesh.C()[celli] - sample);
        if (distance < nearestDistance)
        {
            nearestDistance = distance;
            nearest = celli;
        }
    }
    return nearest;
}

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Publish a converged flat-plate continuum snapshot to Gate 1C DSMC"
    );

    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"

    Foam::volScalarField pressure
    (
        Foam::IOobject
        (
            "p",
            runTime.timeName(),
            mesh,
            Foam::IOobject::MUST_READ,
            Foam::IOobject::NO_WRITE
        ),
        mesh
    );
    Foam::volScalarField temperature
    (
        Foam::IOobject
        (
            "T",
            runTime.timeName(),
            mesh,
            Foam::IOobject::MUST_READ,
            Foam::IOobject::NO_WRITE
        ),
        mesh
    );
    Foam::volVectorField velocity
    (
        Foam::IOobject
        (
            "U",
            runTime.timeName(),
            mesh,
            Foam::IOobject::MUST_READ,
            Foam::IOobject::NO_WRITE
        ),
        mesh
    );

    std::vector<gate1c::State> states;
    states.reserve(gate1c::couplingPointCount);
    double minimumDensity = Foam::GREAT;
    double maximumDensity = 0.0;
    double minimumTemperature = Foam::GREAT;
    double maximumTemperature = 0.0;

    for (int pointIndex = 0;
         pointIndex < gate1c::couplingPointCount;
         ++pointIndex)
    {
        const Foam::label celli = nearestCell
        (
            mesh,
            gate1c::continuumSamplePoint(pointIndex)
        );
        if (celli < 0)
        {
            Foam::Info<< "GATE1C_FAIL role=publisher reason=no_sample_cell"
                      << " point=" << pointIndex << Foam::endl;
            return 2;
        }

        gate1c::State state;
        state.numberDensity = pressure[celli]/(boltzmann*temperature[celli]);
        state.ux = velocity[celli].x();
        state.uy = velocity[celli].y();
        state.uz = velocity[celli].z();
        state.temperature = temperature[celli];
        if (!state.physical())
        {
            Foam::Info<< "GATE1C_FAIL role=publisher reason=nonphysical_state"
                      << " point=" << pointIndex << Foam::endl;
            return 2;
        }

        minimumDensity = std::min(minimumDensity, state.numberDensity);
        maximumDensity = std::max(maximumDensity, state.numberDensity);
        minimumTemperature = std::min(minimumTemperature, state.temperature);
        maximumTemperature = std::max(maximumTemperature, state.temperature);
        states.push_back(state);
    }

    Foam::Info<< "GATE1C_PUBLISHER_SNAPSHOT time=" << runTime.timeName()
              << " points=" << states.size()
              << " number_density_min=" << minimumDensity
              << " number_density_max=" << maximumDensity
              << " temperature_min=" << minimumTemperature
              << " temperature_max=" << maximumTemperature
              << Foam::endl;

    mui::uniface3d interface("mpi://continuum/gate1c");
    for (int couplingStep = 1;
         couplingStep <= gate1c::kineticSteps;
         ++couplingStep)
    {
        for (int pointIndex = 0;
             pointIndex < gate1c::couplingPointCount;
             ++pointIndex)
        {
            gate1c::pushState
            (
                interface,
                gate1c::transportPoint(pointIndex),
                states[pointIndex]
            );
        }
        interface.commit(couplingStep);

        const double acknowledgement =
            gate1c::fetchAcknowledgement(interface, couplingStep);
        if
        (
            !std::isfinite(acknowledgement)
         || std::abs(acknowledgement - couplingStep) > 1.0e-12
        )
        {
            Foam::Info<< "GATE1C_FAIL role=publisher reason=acknowledgement"
                      << " step=" << couplingStep
                      << " value=" << acknowledgement << Foam::endl;
            return 2;
        }
    }

    Foam::Info<< "GATE1C_PASS role=publisher steps="
              << gate1c::kineticSteps
              << " points=" << states.size() << Foam::endl;
    return 0;
}
