// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace
{

constexpr int nx = 40;
constexpr int ny = 20;
constexpr int cellCount = nx*ny;
constexpr double length = 0.1;
constexpr double height = 0.05;
constexpr double boltzmann = 1.380649e-23;

struct State
{
    double indicator = 0.0;
    double numberDensity = 0.0;
    Foam::vector velocity = Foam::vector::zero;
    double temperature = 0.0;

    bool physical() const
    {
        return std::isfinite(indicator) && indicator >= 0.0
            && std::isfinite(numberDensity) && numberDensity > 0.0
            && std::isfinite(velocity.x())
            && std::isfinite(velocity.y())
            && std::isfinite(velocity.z())
            && std::isfinite(temperature) && temperature > 0.0;
    }
};

using ParticleId = std::pair<Foam::label, Foam::label>;

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

std::vector<std::vector<State>> readFrames(const std::string& path)
{
    std::ifstream input(path.c_str());
    if (!input)
    {
        throw std::runtime_error("cannot open indicator CSV");
    }

    std::map<int, std::vector<State>> byFrame;
    std::map<int, std::vector<bool>> seen;
    std::string line;
    if (!std::getline(input, line) || line !=
        "frame,time,cell,i,j,x,y,indicator,n,ux,uy,uz,T")
    {
        throw std::runtime_error("unexpected indicator CSV header");
    }
    while (std::getline(input, line))
    {
        if (line.empty())
        {
            continue;
        }
        const std::vector<std::string> field = split(line);
        if (field.size() != 13)
        {
            throw std::runtime_error("unexpected indicator CSV row");
        }
        const int frame = std::stoi(field[0]);
        const int cell = std::stoi(field[2]);
        const int i = std::stoi(field[3]);
        const int j = std::stoi(field[4]);
        if
        (
            frame < 0 || cell < 0 || cell >= cellCount
         || i != cell % nx || j != cell/nx
        )
        {
            throw std::runtime_error("invalid indicator CSV addressing");
        }
        if (byFrame.find(frame) == byFrame.end())
        {
            byFrame[frame] = std::vector<State>(cellCount);
            seen[frame] = std::vector<bool>(cellCount, false);
        }
        if (seen[frame][cell])
        {
            throw std::runtime_error("duplicate indicator CSV cell");
        }
        seen[frame][cell] = true;
        State& state = byFrame[frame][cell];
        state.indicator = std::stod(field[7]);
        state.numberDensity = std::stod(field[8]);
        state.velocity = Foam::vector
        (
            std::stod(field[9]),
            std::stod(field[10]),
            std::stod(field[11])
        );
        state.temperature = std::stod(field[12]);
        if (!state.physical())
        {
            throw std::runtime_error("nonphysical indicator CSV state");
        }
    }

    if (byFrame.size() != 9)
    {
        throw std::runtime_error("Gate 2 requires exactly nine replay frames");
    }
    std::vector<std::vector<State>> frames;
    for (int frame = 0; frame < 9; ++frame)
    {
        if
        (
            byFrame.find(frame) == byFrame.end()
         || std::find(seen[frame].begin(), seen[frame].end(), false)
            != seen[frame].end()
        )
        {
            throw std::runtime_error("incomplete indicator CSV frame");
        }
        frames.push_back(byFrame[frame]);
    }
    return frames;
}

std::vector<bool> hystereticMask
(
    const std::vector<State>& states,
    const std::vector<bool>& previous,
    const double activationThreshold,
    const double deactivationThreshold,
    const int minimumLayers,
    const int haloLayers
)
{
    std::vector<bool> result(cellCount, false);
    for (int i = 0; i < nx; ++i)
    {
        int top = -1;
        for (int j = 0; j < ny; ++j)
        {
            const int cell = j*nx + i;
            const double threshold = previous[cell]
                ? deactivationThreshold : activationThreshold;
            if (states[cell].indicator >= threshold)
            {
                top = j;
            }
        }
        const int layers = std::min
        (
            ny,
            std::max(minimumLayers, top < 0 ? 0 : top + 1 + haloLayers)
        );
        for (int j = 0; j < layers; ++j)
        {
            result[j*nx + i] = true;
        }
    }
    return result;
}

Foam::label seedCell
(
    Foam::dsmcCloud& cloud,
    const Foam::label meshCell,
    const State& target
)
{
    const double expectedParcels =
        target.numberDensity*cloud.mesh().V()[meshCell]/cloud.nParticle();
    const Foam::label groups = std::max
    (
        Foam::label(1),
        static_cast<Foam::label>(std::floor(expectedParcels/6.0 + 0.5))
    );
    const double moleculeMass = cloud.constProps(0).mass();
    const double thermalSpeed = std::sqrt
    (
        3.0*boltzmann*target.temperature/moleculeMass
    );
    const Foam::vector offsets[6] =
    {
        Foam::vector( thermalSpeed, 0, 0),
        Foam::vector(-thermalSpeed, 0, 0),
        Foam::vector(0,  thermalSpeed, 0),
        Foam::vector(0, -thermalSpeed, 0),
        Foam::vector(0, 0,  thermalSpeed),
        Foam::vector(0, 0, -thermalSpeed)
    };
    const Foam::point position = cloud.mesh().C()[meshCell];
    for (Foam::label group = 0; group < groups; ++group)
    {
        for (int packet = 0; packet < 6; ++packet)
        {
            cloud.addNewParcel
            (
                position, meshCell, target.velocity + offsets[packet], 0.0, 0
            );
        }
    }
    return 6*groups;
}

double auditActivatedState
(
    const Foam::dsmcCloud& cloud,
    const std::vector<bool>& newlyActivated,
    const std::vector<State>& states,
    const std::vector<Foam::label>& meshToLogical,
    const std::vector<Foam::label>& logicalToMesh
)
{
    std::vector<Foam::label> count(cellCount, 0);
    std::vector<Foam::vector> velocitySum(cellCount, Foam::vector::zero);
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        const int logical = meshToLogical[parcel.cell()];
        if (newlyActivated[logical])
        {
            ++count[logical];
            velocitySum[logical] += parcel.U();
        }
    }

    std::vector<double> squaredSpeed(cellCount, 0.0);
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        const int logical = meshToLogical[parcel.cell()];
        if (newlyActivated[logical] && count[logical] > 0)
        {
            const Foam::vector mean = velocitySum[logical]/count[logical];
            squaredSpeed[logical] += Foam::magSqr(parcel.U() - mean);
        }
    }

    double maximumZ = 0.0;
    const double moleculeMass = cloud.constProps(0).mass();
    for (int logical = 0; logical < cellCount; ++logical)
    {
        if (!newlyActivated[logical])
        {
            continue;
        }
        const Foam::label parcels = count[logical];
        if (parcels < 6)
        {
            return Foam::GREAT;
        }
        const Foam::label meshCell = logicalToMesh[logical];
        const State& target = states[logical];
        const double observedDensity =
            parcels*cloud.nParticle()/cloud.mesh().V()[meshCell];
        const Foam::vector observedVelocity = velocitySum[logical]/parcels;
        const double observedTemperature = moleculeMass*squaredSpeed[logical]
            /(3.0*boltzmann*parcels);
        const double densityZ =
            std::abs(observedDensity/target.numberDensity - 1.0)
           *std::sqrt(static_cast<double>(parcels));
        const double velocitySigma = std::sqrt
        (
            3.0*boltzmann*target.temperature/(moleculeMass*parcels)
        );
        const double velocityZ =
            Foam::mag(observedVelocity - target.velocity)/velocitySigma;
        const double temperatureSigma = std::sqrt
        (
            2.0/(3.0*parcels)
        );
        const double temperatureZ =
            std::abs(observedTemperature/target.temperature - 1.0)
           /temperatureSigma;
        maximumZ = std::max
        (
            maximumZ,
            std::max(densityZ, std::max(velocityZ, temperatureZ))
        );
    }
    return maximumZ;
}

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Audit Gate 2 hysteresis and parcel reuse on a real v2312 dsmcCloud"
    );

    #define NO_CONTROL
    #include "postProcess.H"
    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"
    #include "createFields.H"

    const char* csvValue = std::getenv("GATE2_INDICATOR_CSV");
    if (csvValue == nullptr)
    {
        Foam::Info<< "GATE2_FAIL role=particle_manager reason=environment"
                  << Foam::endl;
        return 2;
    }

    Foam::IOdictionary properties
    (
        Foam::IOobject
        (
            "gate2Properties", runTime.system(), mesh,
            Foam::IOobject::MUST_READ, Foam::IOobject::NO_WRITE
        )
    );
    const double activationThreshold = Foam::readScalar
    (
        properties.lookup("activationThreshold")
    );
    const double deactivationThreshold = Foam::readScalar
    (
        properties.lookup("deactivationThreshold")
    );
    const int minimumLayers = Foam::readLabel
    (
        properties.lookup("minimumLayers")
    );
    const int haloLayers = Foam::readLabel(properties.lookup("haloLayers"));
    const double maximumOverlapZ = Foam::readScalar
    (
        properties.lookup("maximumOverlapZ")
    );
    if
    (
        !(activationThreshold > deactivationThreshold)
     || deactivationThreshold < 0.0
     || minimumLayers < 1 || minimumLayers > ny
     || haloLayers < 0 || maximumOverlapZ <= 0.0
    )
    {
        Foam::Info<< "GATE2_FAIL role=particle_manager reason=properties"
                  << Foam::endl;
        return 2;
    }

    std::vector<std::vector<State>> frames;
    try
    {
        frames = readFrames(csvValue);
    }
    catch (const std::exception& error)
    {
        Foam::Info<< "GATE2_FAIL role=particle_manager reason=csv"
                  << " detail=" << error.what() << Foam::endl;
        return 2;
    }

    std::vector<Foam::label> logicalToMesh(cellCount, -1);
    std::vector<Foam::label> meshToLogical(mesh.nCells(), -1);
    const double dx = length/nx;
    const double dy = height/ny;
    forAll(mesh.C(), meshCell)
    {
        const Foam::point& centre = mesh.C()[meshCell];
        const int i = static_cast<int>(std::floor(centre.x()/dx));
        const int j = static_cast<int>(std::floor(centre.y()/dy));
        if (i < 0 || i >= nx || j < 0 || j >= ny)
        {
            Foam::Info<< "GATE2_FAIL role=particle_manager reason=mesh_mapping"
                      << Foam::endl;
            return 2;
        }
        const int logical = j*nx + i;
        if (logicalToMesh[logical] >= 0)
        {
            Foam::Info<< "GATE2_FAIL role=particle_manager reason=mesh_duplicate"
                      << Foam::endl;
            return 2;
        }
        logicalToMesh[logical] = meshCell;
        meshToLogical[meshCell] = logical;
    }
    if
    (
        mesh.nCells() != cellCount
     || std::find(logicalToMesh.begin(), logicalToMesh.end(), -1)
        != logicalToMesh.end()
    )
    {
        Foam::Info<< "GATE2_FAIL role=particle_manager reason=mesh_size"
                  << " expected=" << cellCount
                  << " actual=" << mesh.nCells() << Foam::endl;
        return 2;
    }

    dsmc.clear();
    std::vector<bool> previous(cellCount, false);
    Foam::label dynamicActivated = 0;
    Foam::label totalDeactivated = 0;
    Foam::label totalRetained = 0;
    double observedMaximumZ = 0.0;

    for (int frame = 0; frame < static_cast<int>(frames.size()); ++frame)
    {
        const std::vector<bool> current = hystereticMask
        (
            frames[frame], previous,
            activationThreshold, deactivationThreshold,
            minimumLayers, haloLayers
        );
        std::vector<bool> newlyActivated(cellCount, false);
        std::vector<bool> deactivated(cellCount, false);
        std::vector<bool> retained(cellCount, false);
        Foam::label activatedCells = 0;
        Foam::label deactivatedCells = 0;
        Foam::label retainedCells = 0;
        Foam::label activeCells = 0;
        for (int cell = 0; cell < cellCount; ++cell)
        {
            newlyActivated[cell] = current[cell] && !previous[cell];
            deactivated[cell] = previous[cell] && !current[cell];
            retained[cell] = previous[cell] && current[cell];
            activatedCells += newlyActivated[cell] ? 1 : 0;
            deactivatedCells += deactivated[cell] ? 1 : 0;
            retainedCells += retained[cell] ? 1 : 0;
            activeCells += current[cell] ? 1 : 0;
        }
        int minimumColumnLayers = ny;
        int maximumColumnLayers = 0;
        for (int i = 0; i < nx; ++i)
        {
            int layers = 0;
            for (int j = 0; j < ny; ++j)
            {
                layers += current[j*nx + i] ? 1 : 0;
            }
            minimumColumnLayers = std::min(minimumColumnLayers, layers);
            maximumColumnLayers = std::max(maximumColumnLayers, layers);
        }

        std::set<ParticleId> retainedBefore;
        for
        (
            Foam::dsmcCloud::const_iterator iter = dsmc.cbegin();
            iter != dsmc.cend();
            ++iter
        )
        {
            const Foam::dsmcParcel& parcel = iter();
            const int logical = meshToLogical[parcel.cell()];
            if (retained[logical])
            {
                retainedBefore.insert
                (
                    ParticleId(parcel.origProc(), parcel.origId())
                );
            }
        }

        for
        (
            Foam::dsmcCloud::iterator iter = dsmc.begin();
            iter != dsmc.end();
        )
        {
            Foam::dsmcParcel& parcel = iter();
            ++iter;
            if (deactivated[meshToLogical[parcel.cell()]])
            {
                dsmc.deleteParticle(parcel);
            }
        }

        Foam::label created = 0;
        for (int logical = 0; logical < cellCount; ++logical)
        {
            if (newlyActivated[logical])
            {
                created += seedCell
                (
                    dsmc, logicalToMesh[logical], frames[frame][logical]
                );
            }
        }

        std::set<ParticleId> retainedAfter;
        Foam::label inactiveParcels = 0;
        for
        (
            Foam::dsmcCloud::const_iterator iter = dsmc.cbegin();
            iter != dsmc.cend();
            ++iter
        )
        {
            const Foam::dsmcParcel& parcel = iter();
            const int logical = meshToLogical[parcel.cell()];
            if (!current[logical])
            {
                ++inactiveParcels;
            }
            if (retained[logical])
            {
                retainedAfter.insert
                (
                    ParticleId(parcel.origProc(), parcel.origId())
                );
            }
        }
        if (retainedBefore != retainedAfter)
        {
            Foam::Info<< "GATE2_FAIL role=particle_manager"
                      << " reason=retained_particle_identity"
                      << " frame=" << frame << Foam::endl;
            return 2;
        }

        const double frameMaximumZ = auditActivatedState
        (
            dsmc, newlyActivated, frames[frame],
            meshToLogical, logicalToMesh
        );
        observedMaximumZ = std::max(observedMaximumZ, frameMaximumZ);
        if (!std::isfinite(frameMaximumZ) || frameMaximumZ > maximumOverlapZ)
        {
            Foam::Info<< "GATE2_FAIL role=particle_manager"
                      << " reason=overlap_uncertainty"
                      << " frame=" << frame
                      << " max_z=" << frameMaximumZ << Foam::endl;
            return 2;
        }
        if
        (
            inactiveParcels != 0
         || (activatedCells == 0 && created != 0)
         || (activatedCells > 0 && created == 0)
        )
        {
            Foam::Info<< "GATE2_FAIL role=particle_manager"
                      << " reason=transition_accounting"
                      << " frame=" << frame << Foam::endl;
            return 2;
        }

        if (frame > 0)
        {
            dynamicActivated += activatedCells;
        }
        totalDeactivated += deactivatedCells;
        totalRetained += retainedCells;
        Foam::Info<< "GATE2_FRAME frame=" << frame
                  << " active=" << activeCells
                  << " min_layers=" << minimumColumnLayers
                  << " max_layers=" << maximumColumnLayers
                  << " activated=" << activatedCells
                  << " deactivated=" << deactivatedCells
                  << " retained=" << retainedCells
                  << " reused_parcels=" << retainedAfter.size()
                  << " created_parcels=" << created
                  << " inactive_parcels=" << inactiveParcels
                  << " max_overlap_z=" << frameMaximumZ << Foam::endl;
        previous = current;
    }

    const bool pass =
        dynamicActivated > 0
     && totalDeactivated > 0
     && totalRetained > 0
     && observedMaximumZ <= maximumOverlapZ;
    Foam::Info<< (pass ? "GATE2_PASS" : "GATE2_FAIL")
              << " role=particle_manager"
              << " frames=" << frames.size()
              << " activation_threshold=" << activationThreshold
              << " deactivation_threshold=" << deactivationThreshold
              << " dynamic_activated=" << dynamicActivated
              << " deactivated=" << totalDeactivated
              << " retained=" << totalRetained
              << " max_overlap_z=" << observedMaximumZ
              << " external_reference_used=false" << Foam::endl;
    return pass ? 0 : 2;
}
