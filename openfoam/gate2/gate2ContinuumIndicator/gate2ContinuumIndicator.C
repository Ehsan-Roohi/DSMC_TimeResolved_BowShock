// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <string>
#include <vector>

namespace
{

constexpr int nx = 40;
constexpr int ny = 20;
constexpr int cellCount = nx*ny;
constexpr double length = 0.1;
constexpr double height = 0.05;
constexpr double boltzmann = 1.380649e-23;
constexpr double moleculeMass = 6.6335209e-26;
constexpr double moleculeDiameter = 4.17e-10;

struct Aggregate
{
    double indicator = 0.0;
    double numberDensity = 0.0;
    Foam::vector velocity = Foam::vector::zero;
    double temperature = 0.0;
    int samples = 0;
};

bool physical(const double value)
{
    return std::isfinite(value) && value > 0.0;
}

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Extract the Gate 2 continuum-breakdown indicator on the DSMC grid"
    );

    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"

    Foam::volScalarField pressure
    (
        Foam::IOobject
        (
            "p", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::NO_WRITE
        ),
        mesh
    );
    Foam::volScalarField temperature
    (
        Foam::IOobject
        (
            "T", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::NO_WRITE
        ),
        mesh
    );
    Foam::volVectorField velocity
    (
        Foam::IOobject
        (
            "U", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::NO_WRITE
        ),
        mesh
    );

    const Foam::tmp<Foam::volVectorField> pressureGradient =
        Foam::fvc::grad(pressure);
    const Foam::tmp<Foam::volVectorField> temperatureGradient =
        Foam::fvc::grad(temperature);
    const Foam::tmp<Foam::volTensorField> velocityGradient =
        Foam::fvc::grad(velocity);

    std::vector<Aggregate> aggregates(cellCount);
    const double dx = length/nx;
    const double dy = height/ny;
    const double pi = std::acos(-1.0);

    forAll(mesh.C(), celli)
    {
        const Foam::point& centre = mesh.C()[celli];
        const int i = static_cast<int>(std::floor(centre.x()/dx));
        const int j = static_cast<int>(std::floor(centre.y()/dy));
        if (i < 0 || i >= nx || j < 0 || j >= ny)
        {
            Foam::Info<< "GATE2_FAIL role=indicator reason=cell_mapping"
                      << " cell=" << celli << " centre=" << centre
                      << Foam::endl;
            return 2;
        }

        const double p = pressure[celli];
        const double T = temperature[celli];
        if (!physical(p) || !physical(T))
        {
            Foam::Info<< "GATE2_FAIL role=indicator reason=nonphysical_state"
                      << " cell=" << celli << Foam::endl;
            return 2;
        }

        const double n = p/(boltzmann*T);
        const double meanFreePath = 1.0/
        (
            std::sqrt(2.0)*pi*moleculeDiameter*moleculeDiameter*n
        );
        const Foam::vector normalizedDensityGradient =
            pressureGradient()[celli]/p
          - temperatureGradient()[celli]/T;
        const double thermalSpeed =
            std::sqrt(2.0*boltzmann*T/moleculeMass);
        const double velocityScale = std::max
        (
            Foam::mag(velocity[celli]), thermalSpeed
        );
        const double knDensity =
            meanFreePath*Foam::mag(normalizedDensityGradient);
        const double knTemperature =
            meanFreePath*Foam::mag(temperatureGradient()[celli])/T;
        const double knVelocity =
            meanFreePath*Foam::mag(velocityGradient()[celli])/velocityScale;
        const double indicator = std::max
        (
            knDensity, std::max(knTemperature, knVelocity)
        );
        if (!std::isfinite(indicator) || !physical(n))
        {
            Foam::Info<< "GATE2_FAIL role=indicator reason=nonfinite_indicator"
                      << " cell=" << celli << Foam::endl;
            return 2;
        }

        Aggregate& aggregate = aggregates[j*nx + i];
        aggregate.indicator = std::max(aggregate.indicator, indicator);
        aggregate.numberDensity += n;
        aggregate.velocity += velocity[celli];
        aggregate.temperature += T;
        ++aggregate.samples;
    }

    const char* outputValue = std::getenv("GATE2_INDICATOR_OUTPUT");
    const char* frameValue = std::getenv("GATE2_FRAME");
    if (outputValue == nullptr || frameValue == nullptr)
    {
        Foam::Info<< "GATE2_FAIL role=indicator reason=environment"
                  << Foam::endl;
        return 2;
    }
    const int frame = std::atoi(frameValue);
    if (frame < 0)
    {
        Foam::Info<< "GATE2_FAIL role=indicator reason=frame"
                  << Foam::endl;
        return 2;
    }

    std::ofstream output
    (
        outputValue,
        frame == 0 ? std::ios::out : (std::ios::out | std::ios::app)
    );
    if (!output)
    {
        Foam::Info<< "GATE2_FAIL role=indicator reason=output"
                  << Foam::endl;
        return 2;
    }
    if (frame == 0)
    {
        output << "frame,time,cell,i,j,x,y,indicator,n,ux,uy,uz,T\n";
    }
    output << std::setprecision(17);

    double minimumIndicator = Foam::GREAT;
    double maximumIndicator = 0.0;
    int aboveActivation = 0;
    for (int cell = 0; cell < cellCount; ++cell)
    {
        Aggregate& aggregate = aggregates[cell];
        if (aggregate.samples != 4)
        {
            Foam::Info<< "GATE2_FAIL role=indicator reason=aggregation"
                      << " cell=" << cell
                      << " samples=" << aggregate.samples << Foam::endl;
            return 2;
        }
        const double inverseSamples = 1.0/aggregate.samples;
        aggregate.numberDensity *= inverseSamples;
        aggregate.velocity *= inverseSamples;
        aggregate.temperature *= inverseSamples;
        minimumIndicator = std::min(minimumIndicator, aggregate.indicator);
        maximumIndicator = std::max(maximumIndicator, aggregate.indicator);
        if (aggregate.indicator >= 0.05)
        {
            ++aboveActivation;
        }
        const int i = cell % nx;
        const int j = cell/nx;
        output << frame << ',' << runTime.timeName() << ',' << cell << ','
               << i << ',' << j << ',' << (i + 0.5)*dx << ','
               << (j + 0.5)*dy << ',' << aggregate.indicator << ','
               << aggregate.numberDensity << ',' << aggregate.velocity.x()
               << ',' << aggregate.velocity.y() << ','
               << aggregate.velocity.z() << ',' << aggregate.temperature
               << '\n';
    }

    Foam::Info<< "GATE2_INDICATOR frame=" << frame
              << " time=" << runTime.timeName()
              << " cells=" << cellCount
              << " min=" << minimumIndicator
              << " max=" << maximumIndicator
              << " above_activation=" << aboveActivation << Foam::endl;
    Foam::Info<< "GATE2_PASS role=indicator frame=" << frame << Foam::endl;
    return 0;
}
