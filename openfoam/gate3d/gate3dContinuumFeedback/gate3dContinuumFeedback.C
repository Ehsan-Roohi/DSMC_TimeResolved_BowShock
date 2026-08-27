// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace
{

constexpr double gasConstant = 8.31446261815324e3/39.948;
constexpr double constantVolumeHeatCapacity = 1.5*gasConstant;
constexpr double maximumFractionalCorrection = 0.01;
constexpr double continuumRadialWidth = (0.05 - 0.01)/32.0;

struct Feedback
{
    int face;
    double theta;
    double radius;
    double wallArea;
    double indicator;
    int activeLayers;
    double mass;
    Foam::vector momentum;
    double energy;
    Foam::label cell;
};

std::vector<std::string> split(const std::string& line)
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

Foam::label nearestCell(const Foam::fvMesh& mesh, const Foam::point& sample)
{
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

std::vector<Feedback> readFeedback
(
    const std::string& path,
    const Foam::fvMesh& mesh
)
{
    std::ifstream input(path.c_str());
    std::string line;
    const std::string header =
        "face,theta,interface_radius,wall_area,indicator,active_layers,"
        "mass,momentum_x,momentum_y,momentum_z,energy";
    if (!input || !std::getline(input, line) || line != header)
    {
        throw std::runtime_error("invalid Gate-3D feedback CSV header");
    }
    std::vector<Feedback> result;
    std::set<Foam::label> selectedCells;
    while (std::getline(input, line))
    {
        if (line.empty()) continue;
        const std::vector<std::string> field = split(line);
        if (field.size() != 11)
        {
            throw std::runtime_error("invalid Gate-3D feedback CSV row");
        }
        Feedback item;
        item.face = std::stoi(field[0]);
        item.theta = std::stod(field[1]);
        item.radius = std::stod(field[2]);
        item.wallArea = std::stod(field[3]);
        item.indicator = std::stod(field[4]);
        item.activeLayers = std::stoi(field[5]);
        item.mass = std::stod(field[6]);
        item.momentum = Foam::vector
        (
            std::stod(field[7]), std::stod(field[8]), std::stod(field[9])
        );
        item.energy = std::stod(field[10]);
        const Foam::point sample
        (
            (item.radius + 0.5*continuumRadialWidth)*std::cos(item.theta),
            (item.radius + 0.5*continuumRadialWidth)*std::sin(item.theta),
            0.0
        );
        item.cell = nearestCell(mesh, sample);
        if
        (
            item.face != static_cast<int>(result.size())
         || item.cell < 0
         || item.wallArea <= 0.0
         || item.activeLayers < 4
         || item.activeLayers > 8
         || std::abs(item.mass) > 1.0e-30
         || !std::isfinite(item.theta)
         || !std::isfinite(item.radius)
         || !std::isfinite(item.indicator)
         || !std::isfinite(item.momentum.x())
         || !std::isfinite(item.momentum.y())
         || !std::isfinite(item.momentum.z())
         || !std::isfinite(item.energy)
         || !selectedCells.insert(item.cell).second
        )
        {
            throw std::runtime_error("invalid or duplicate Gate-3D feedback target");
        }
        result.push_back(item);
    }
    if (result.size() != 64)
    {
        throw std::runtime_error("Gate-3D feedback requires 64 physical faces");
    }
    return result;
}

double relativeDifference(const double actual, const double expected)
{
    return std::abs(actual - expected)/std::max
    (
        1.0, std::max(std::abs(actual), std::abs(expected))
    );
}

} // namespace

int main(int argc, char* argv[])
{
    Foam::argList::addNote
    (
        "Apply relaxed DSMC physical feedback to a Gate-3D continuum snapshot"
    );
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"

    const char* csvValue = std::getenv("GATE3D_FEEDBACK_CSV");
    if (csvValue == nullptr)
    {
        Foam::Info<< "GATE3D_FAIL role=continuum_feedback reason=environment"
                  << Foam::endl;
        return 2;
    }

    Foam::volScalarField pressure
    (
        Foam::IOobject
        (
            "p", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::AUTO_WRITE
        ),
        mesh
    );
    Foam::volScalarField temperature
    (
        Foam::IOobject
        (
            "T", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::AUTO_WRITE
        ),
        mesh
    );
    Foam::volVectorField velocity
    (
        Foam::IOobject
        (
            "U", runTime.timeName(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::AUTO_WRITE
        ),
        mesh
    );

    std::vector<Feedback> feedback;
    try
    {
        feedback = readFeedback(csvValue, mesh);
    }
    catch (const std::exception& error)
    {
        Foam::Info<< "GATE3D_FAIL role=continuum_feedback reason=csv"
                  << " detail=" << error.what() << Foam::endl;
        return 2;
    }

    double scale = 1.0;
    Foam::vector requestedMomentum = Foam::vector::zero;
    double requestedEnergy = 0.0;
    for (std::size_t face = 0; face < feedback.size(); ++face)
    {
        const Feedback& item = feedback[face];
        const double p = pressure[item.cell];
        const double T = temperature[item.cell];
        const double rho = p/(gasConstant*T);
        const double volume = mesh.V()[item.cell];
        const double velocityScale = std::max
        (
            Foam::mag(velocity[item.cell]),
            std::sqrt(gasConstant*T)
        );
        if
        (
            !std::isfinite(rho) || rho <= 0.0
         || !std::isfinite(volume) || volume <= 0.0
         || !std::isfinite(T) || T <= 0.0
        )
        {
            Foam::Info<< "GATE3D_FAIL role=continuum_feedback"
                      << " reason=nonphysical_target face=" << face
                      << Foam::endl;
            return 2;
        }
        const double momentumRatio = Foam::mag(item.momentum)/std::max
        (
            rho*volume*velocityScale, Foam::VSMALL
        );
        const double energyRatio = std::abs(item.energy)/std::max
        (
            rho*volume*constantVolumeHeatCapacity*T, Foam::VSMALL
        );
        const double ratio = std::max(momentumRatio, energyRatio);
        if (ratio > maximumFractionalCorrection)
        {
            scale = std::min(scale, maximumFractionalCorrection/ratio);
        }
        requestedMomentum -= item.momentum;
        requestedEnergy -= item.energy;
    }
    if (!std::isfinite(scale) || scale <= 0.0 || scale > 1.0)
    {
        Foam::Info<< "GATE3D_FAIL role=continuum_feedback reason=feedback_scale"
                  << " value=" << scale << Foam::endl;
        return 2;
    }

    Foam::vector appliedMomentum = Foam::vector::zero;
    double appliedEnergy = 0.0;
    double maximumTemperatureChange = 0.0;
    double maximumVelocityChange = 0.0;
    for (std::size_t face = 0; face < feedback.size(); ++face)
    {
        const Feedback& item = feedback[face];
        const double oldTemperature = temperature[item.cell];
        const Foam::vector oldVelocity = velocity[item.cell];
        const double rho = pressure[item.cell]
            /(gasConstant*oldTemperature);
        const double volume = mesh.V()[item.cell];
        const Foam::vector deltaMomentum = -scale*item.momentum;
        const double deltaEnergy = -scale*item.energy;
        const Foam::vector newVelocity = oldVelocity
            + deltaMomentum/(rho*volume);
        const double oldEnergyDensity = rho*
        (
            constantVolumeHeatCapacity*oldTemperature
          + 0.5*Foam::magSqr(oldVelocity)
        );
        const double newEnergyDensity = oldEnergyDensity
            + deltaEnergy/volume;
        const double newTemperature =
        (
            newEnergyDensity/rho - 0.5*Foam::magSqr(newVelocity)
        )/constantVolumeHeatCapacity;
        if (!std::isfinite(newTemperature) || newTemperature <= 0.0)
        {
            Foam::Info<< "GATE3D_FAIL role=continuum_feedback"
                      << " reason=nonphysical_corrected_state face=" << face
                      << Foam::endl;
            return 2;
        }
        velocity[item.cell] = newVelocity;
        temperature[item.cell] = newTemperature;
        pressure[item.cell] = rho*gasConstant*newTemperature;
        maximumVelocityChange = std::max
        (
            maximumVelocityChange,
            Foam::mag(newVelocity - oldVelocity)
        );
        maximumTemperatureChange = std::max
        (
            maximumTemperatureChange,
            std::abs(newTemperature - oldTemperature)
        );
        appliedMomentum += deltaMomentum;
        appliedEnergy += deltaEnergy;
    }

    pressure.correctBoundaryConditions();
    temperature.correctBoundaryConditions();
    velocity.correctBoundaryConditions();
    if (!pressure.write() || !temperature.write() || !velocity.write())
    {
        Foam::Info<< "GATE3D_FAIL role=continuum_feedback reason=field_write"
                  << Foam::endl;
        return 2;
    }
    const Foam::vector expectedMomentum = scale*requestedMomentum;
    const double expectedEnergy = scale*requestedEnergy;
    const double conservationError = std::max
    (
        std::max
        (
            relativeDifference(appliedMomentum.x(), expectedMomentum.x()),
            relativeDifference(appliedMomentum.y(), expectedMomentum.y())
        ),
        std::max
        (
            relativeDifference(appliedMomentum.z(), expectedMomentum.z()),
            relativeDifference(appliedEnergy, expectedEnergy)
        )
    );
    const bool pass =
        conservationError <= 1.0e-12
     && maximumTemperatureChange > 0.0
     && maximumVelocityChange > 0.0;
    Foam::Info<< (pass ? "GATE3D_PASS" : "GATE3D_FAIL")
              << " role=continuum_feedback"
              << " fields_written=true"
              << " target_time=" << runTime.timeName()
              << " faces=" << feedback.size()
              << " feedback_scale=" << scale
              << " applied_momentum_x=" << appliedMomentum.x()
              << " applied_momentum_y=" << appliedMomentum.y()
              << " applied_momentum_z=" << appliedMomentum.z()
              << " applied_energy=" << appliedEnergy
              << " conservation_rel=" << conservationError
              << " max_delta_U=" << maximumVelocityChange
              << " max_delta_T=" << maximumTemperatureChange
              << Foam::endl;
    return pass ? 0 : 2;
}
