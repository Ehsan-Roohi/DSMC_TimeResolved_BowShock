// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"
#ifdef GATE3F_DYNAMIC
#include "Gate3FMui.H"
#elif defined(GATE3E_LIVE)
#include "Gate3EMui.H"
#else
#include "Gate3CMui.H"
#endif

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace
{

constexpr double boltzmann = 1.380649e-23;

#ifdef GATE3E_LIVE
#ifdef GATE3F_DYNAMIC
constexpr const char* liveGateLabel = "GATE3F";
constexpr const char* liveDsmcUri = "mpi://dsmc/gate3f";
#else
constexpr const char* liveGateLabel = "GATE3E";
constexpr const char* liveDsmcUri = "mpi://dsmc/gate3e";
#endif
#endif

Foam::vector tangent(const Foam::vector& inwardNormal)
{
    Foam::vector reference(0, 0, 1);
    Foam::vector result = inwardNormal ^ reference;
    result /= Foam::mag(result);
    return result;
}

#ifndef GATE3F_DYNAMIC
Foam::label injectMappedReservoir
(
    Foam::dsmcCloud& cloud,
    mui::uniface3d& interface,
    const int couplingStep,
    std::vector<double>& accumulators
#ifdef GATE3E_LIVE
    ,
    std::vector<int>& liveLayers,
    int& liveLayerChanges
#endif
)
{
    const Foam::fvMesh& mesh = cloud.mesh();
    const Foam::label patchi = mesh.boundaryMesh().findPatchID("interface");
    if (patchi < 0)
    {
        Foam::Info<< "GATE3C_FAIL role=hybrid reason=missing_interface_patch"
                  << Foam::endl;
        return -1;
    }
    const Foam::polyPatch& patch = mesh.boundaryMesh()[patchi];
    const Foam::pointField::subField faceCentres = patch.faceCentres();
    const Foam::vectorField::subField faceAreas = patch.faceAreas();
    const Foam::scalarField& faceAreaMagnitudes = patch.magFaceAreas();
    const double deltaT = mesh.time().deltaTValue();
    const double moleculeMass = cloud.constProps(0).mass();
    const double equivalentParticles = cloud.nParticle();
    std::vector<bool> mappedPointSeen(gate3c::angularCells, false);
    Foam::label inserted = 0;

    forAll(patch, facei)
    {
        const Foam::point& faceCentre = faceCentres[facei];
        const int pointIndex = gate3c::pointIndex(faceCentre.x(), faceCentre.y());
        if (pointIndex < 0 || pointIndex >= gate3c::angularCells)
        {
            Foam::Info<< "GATE3C_FAIL role=hybrid reason=unmapped_interface_face"
                      << " centre=" << faceCentre << Foam::endl;
            return -1;
        }
        if (mappedPointSeen[pointIndex])
        {
            Foam::Info<< "GATE3C_FAIL role=hybrid reason=duplicate_mapped_point"
                      << " point=" << pointIndex << Foam::endl;
            return -1;
        }
        mappedPointSeen[pointIndex] = true;

        const gate3c::State state = gate3c::fetchState
        (
            interface,
            gate3c::transportPoint(pointIndex),
            couplingStep
        );
        if (!state.physical())
        {
            Foam::Info<< "GATE3C_FAIL role=hybrid reason=nonphysical_mapped_state"
                      << " point=" << pointIndex
                      << " step=" << couplingStep << Foam::endl;
            return -1;
        }
#ifdef GATE3E_LIVE
        const int activeLayers = gate3e::fetchActiveLayers
        (
            interface,
            gate3c::transportPoint(pointIndex),
            couplingStep
        );
        if (activeLayers < 4 || activeLayers > 8)
        {
            Foam::Info<< "GATE3E_FAIL role=dsmc reason=active_layers"
                      << " point=" << pointIndex
                      << " step=" << couplingStep
                      << " value=" << activeLayers << Foam::endl;
            return -1;
        }
        if (liveLayers[pointIndex] != activeLayers)
        {
            liveLayers[pointIndex] = activeLayers;
            ++liveLayerChanges;
        }
#endif

        const Foam::vector inwardNormal =
            -faceAreas[facei]/faceAreaMagnitudes[facei];
        const Foam::vector t1 = tangent(inwardNormal);
        const Foam::vector t2 = inwardNormal ^ t1;
        const Foam::vector reservoirVelocity(state.ux, state.uy, state.uz);
        const double mostProbableSpeed = std::sqrt
        (
            2.0*boltzmann*state.temperature/moleculeMass
        );
        const double sCosTheta =
            (reservoirVelocity & inwardNormal)/mostProbableSpeed;
        const double sqrtPi = std::sqrt(gate3c::pi);
        const double fluxFactor =
        (
            std::exp(-sCosTheta*sCosTheta)
          + sqrtPi*sCosTheta*(1.0 + std::erf(sCosTheta))
        )/(2.0*sqrtPi);

        double& accumulator = accumulators[pointIndex];
        accumulator +=
            faceAreaMagnitudes[facei]
           *(state.numberDensity/equivalentParticles)
           *deltaT*mostProbableSpeed*fluxFactor;
        Foam::label parcelCount = std::max
        (
            static_cast<Foam::label>(accumulator),
            Foam::label(0)
        );
        if
        (
            accumulator - parcelCount
          > cloud.rndGen().sample01<Foam::scalar>()
        )
        {
            ++parcelCount;
        }
        accumulator -= parcelCount;

        const double probabilityA =
            sCosTheta + std::sqrt(sCosTheta*sCosTheta + 2.0);
        const double probabilityB = 0.5*
        (
            1.0
          + sCosTheta*
            (
                sCosTheta - std::sqrt(sCosTheta*sCosTheta + 2.0)
            )
        );
        const double randomScaling =
            sCosTheta < -3.0 ? std::abs(sCosTheta) + 1.0 : 3.0;
        const double tangentialLength =
            faceAreaMagnitudes[facei]/gate3c::kineticSpan;
        const Foam::label globalFace = patch.start() + facei;
        const Foam::label celli = mesh.faceOwner()[globalFace];

        for (Foam::label parceli = 0; parceli < parcelCount; ++parceli)
        {
            const double openIntervalScale = 1.0 - 2.0e-12;
            Foam::point position = faceCentre
                + openIntervalScale*tangentialLength
                 *(cloud.rndGen().sample01<Foam::scalar>() - 0.5)*t1;
            position.z() = openIntervalScale*gate3c::kineticSpan
                *(cloud.rndGen().sample01<Foam::scalar>() - 0.5);
            position += 1.0e-7*gate3c::kineticRadialWidth*inwardNormal;

            double probability = -1.0;
            double normalVelocity = 0.0;
            int attempts = 0;
            do
            {
                const double thermalCandidate = randomScaling*
                (2.0*cloud.rndGen().sample01<Foam::scalar>() - 1.0);
                normalVelocity = thermalCandidate + sCosTheta;
                probability = normalVelocity < 0.0
                    ? -1.0
                    : 2.0*normalVelocity/probabilityA
                     *std::exp
                     (
                         probabilityB - thermalCandidate*thermalCandidate
                     );
                ++attempts;
            }
            while
            (
                probability < cloud.rndGen().sample01<Foam::scalar>()
             && attempts < 100000
            );
            if (attempts >= 100000)
            {
                Foam::Info<< "GATE3C_FAIL role=hybrid"
                          << " reason=inflow_velocity_rejection" << Foam::endl;
                return -1;
            }

            const Foam::vector velocity =
                std::sqrt(boltzmann*state.temperature/moleculeMass)
               *(
                    cloud.rndGen().GaussNormal<Foam::scalar>()*t1
                  + cloud.rndGen().GaussNormal<Foam::scalar>()*t2
                )
              + (t1 & reservoirVelocity)*t1
              + (t2 & reservoirVelocity)*t2
              + mostProbableSpeed*normalVelocity*inwardNormal;
            cloud.addNewParcel(position, celli, velocity, 0.0, 0);
            ++inserted;
        }
    }

    if
    (
        patch.size() != gate3c::angularCells
     || std::find(mappedPointSeen.begin(), mappedPointSeen.end(), false)
        != mappedPointSeen.end()
    )
    {
        Foam::Info<< "GATE3C_FAIL role=hybrid reason=mapped_face_count"
                  << " expected=" << gate3c::angularCells
                  << " actual=" << patch.size() << Foam::endl;
        return -1;
    }
#ifndef GATE3E_LIVE
    gate3c::pushAcknowledgement(interface, couplingStep);
    interface.commit(couplingStep);
#endif
    return inserted;
}
#endif

#ifdef GATE3F_DYNAMIC
using ParticleId = std::pair<Foam::label, Foam::label>;

bool buildDynamicAddressing
(
    const Foam::fvMesh& mesh,
    std::vector<int>& cellPoint,
    std::vector<int>& cellLayer,
    std::vector<Foam::label>& pointLayerToCell
)
{
    cellPoint.assign(mesh.nCells(), -1);
    cellLayer.assign(mesh.nCells(), -1);
    pointLayerToCell.assign
    (
        gate3c::angularCells*muiFoam::kineticMeshLayers,
        Foam::label(-1)
    );
    forAll(mesh.C(), celli)
    {
        const Foam::point centre = mesh.C()[celli];
        const int point = gate3c::pointIndex(centre.x(), centre.y());
        const double radius = std::sqrt
        (
            centre.x()*centre.x() + centre.y()*centre.y()
        );
        const int layer = static_cast<int>
        (
            std::floor
            (
                (radius - gate3c::cylinderRadius)
               /gate3c::kineticRadialWidth
            )
        );
        if
        (
            point < 0 || point >= gate3c::angularCells
         || layer < 0 || layer >= muiFoam::kineticMeshLayers
        )
        {
            return false;
        }
        const int address = point*muiFoam::kineticMeshLayers + layer;
        if (pointLayerToCell[address] >= 0)
        {
            return false;
        }
        cellPoint[celli] = point;
        cellLayer[celli] = layer;
        pointLayerToCell[address] = celli;
    }
    return mesh.nCells()
        == gate3c::angularCells*muiFoam::kineticMeshLayers
        && std::find
        (
            pointLayerToCell.begin(), pointLayerToCell.end(), Foam::label(-1)
        ) == pointLayerToCell.end();
}

bool dynamicCellActive
(
    const Foam::label celli,
    const std::vector<int>& layers,
    const std::vector<int>& cellPoint,
    const std::vector<int>& cellLayer
)
{
    return muiFoam::particleCellActive
    (
        cellLayer[celli], layers[cellPoint[celli]]
    );
}

Foam::label seedDynamicCell
(
    Foam::dsmcCloud& cloud,
    const Foam::label celli,
    const gate3c::State& target
)
{
    const double expectedParcels =
        target.numberDensity*cloud.mesh().V()[celli]/cloud.nParticle();
    const Foam::label groups = static_cast<Foam::label>
    (
        muiFoam::momentPacketGroups(expectedParcels)
    );
    const double moleculeMass = cloud.constProps(0).mass();
    const double thermalSpeed = std::sqrt
    (
        3.0*boltzmann*target.temperature/moleculeMass
    );
    const Foam::vector bulk(target.ux, target.uy, target.uz);
    const Foam::vector offsets[6] =
    {
        Foam::vector( thermalSpeed, 0, 0),
        Foam::vector(-thermalSpeed, 0, 0),
        Foam::vector(0,  thermalSpeed, 0),
        Foam::vector(0, -thermalSpeed, 0),
        Foam::vector(0, 0,  thermalSpeed),
        Foam::vector(0, 0, -thermalSpeed)
    };
    for (Foam::label group = 0; group < groups; ++group)
    {
        for (int packet = 0; packet < 6; ++packet)
        {
            cloud.addNewParcel
            (
                cloud.mesh().C()[celli], celli,
                bulk + offsets[packet], 0.0, 0
            );
        }
    }
    return 6*groups;
}

double auditDynamicActivation
(
    const Foam::dsmcCloud& cloud,
    const std::vector<bool>& newlyActivated,
    const std::vector<gate3c::State>& states,
    const std::vector<int>& cellPoint
)
{
    std::vector<Foam::label> counts(cloud.mesh().nCells(), 0);
    std::vector<Foam::vector>
        velocitySums(cloud.mesh().nCells(), Foam::vector::zero);
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        if (newlyActivated[parcel.cell()])
        {
            ++counts[parcel.cell()];
            velocitySums[parcel.cell()] += parcel.U();
        }
    }
    std::vector<double> squaredSpeed(cloud.mesh().nCells(), 0.0);
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        const Foam::label celli = parcel.cell();
        if (newlyActivated[celli] && counts[celli] > 0)
        {
            const Foam::vector mean = velocitySums[celli]/counts[celli];
            squaredSpeed[celli] += Foam::magSqr(parcel.U() - mean);
        }
    }

    const double moleculeMass = cloud.constProps(0).mass();
    double maximumZ = 0.0;
    forAll(newlyActivated, celli)
    {
        if (!newlyActivated[celli])
        {
            continue;
        }
        const Foam::label parcels = counts[celli];
        if (parcels < 6)
        {
            return Foam::GREAT;
        }
        const gate3c::State& target = states[cellPoint[celli]];
        const double density =
            parcels*cloud.nParticle()/cloud.mesh().V()[celli];
        const Foam::vector velocity = velocitySums[celli]/parcels;
        const double temperature = moleculeMass*squaredSpeed[celli]
            /(3.0*boltzmann*parcels);
        const double densityZ =
            std::abs(density/target.numberDensity - 1.0)
           *std::sqrt(static_cast<double>(parcels));
        const double velocitySigma = std::sqrt
        (
            3.0*boltzmann*target.temperature/(moleculeMass*parcels)
        );
        const double velocityZ = Foam::mag
        (
            velocity - Foam::vector(target.ux, target.uy, target.uz)
        )/velocitySigma;
        const double temperatureZ =
            std::abs(temperature/target.temperature - 1.0)
           /std::sqrt(2.0/(3.0*parcels));
        maximumZ = std::max
        (
            maximumZ,
            std::max(densityZ, std::max(velocityZ, temperatureZ))
        );
    }
    return maximumZ;
}

Foam::label injectDynamicReservoirPoint
(
    Foam::dsmcCloud& cloud,
    const gate3c::State& state,
    const int pointIndex,
    const int continuumLayers,
    const Foam::label ownerCell,
    double& accumulator
)
{
    const double deltaT = cloud.mesh().time().deltaTValue();
    const double moleculeMass = cloud.constProps(0).mass();
    const double radius = gate3f::particleInterfaceRadius(continuumLayers);
    const double area = radius*gate3c::angularWidth*gate3c::kineticSpan;
    const double theta = gate3c::centreAngle(pointIndex);
    const Foam::vector outward(std::cos(theta), std::sin(theta), 0.0);
    const Foam::vector inwardNormal = -outward;
    const Foam::vector t1 = tangent(inwardNormal);
    const Foam::vector t2 = inwardNormal ^ t1;
    const Foam::vector reservoirVelocity(state.ux, state.uy, state.uz);
    const double mostProbableSpeed = std::sqrt
    (
        2.0*boltzmann*state.temperature/moleculeMass
    );
    const double sCosTheta =
        (reservoirVelocity & inwardNormal)/mostProbableSpeed;
    const double sqrtPi = std::sqrt(gate3c::pi);
    const double fluxFactor =
    (
        std::exp(-sCosTheta*sCosTheta)
      + sqrtPi*sCosTheta*(1.0 + std::erf(sCosTheta))
    )/(2.0*sqrtPi);
    accumulator += area*(state.numberDensity/cloud.nParticle())
        *deltaT*mostProbableSpeed*fluxFactor;
    Foam::label parcelCount = std::max
    (
        static_cast<Foam::label>(accumulator), Foam::label(0)
    );
    if
    (
        accumulator - parcelCount
      > cloud.rndGen().sample01<Foam::scalar>()
    )
    {
        ++parcelCount;
    }
    accumulator -= parcelCount;

    const double probabilityA =
        sCosTheta + std::sqrt(sCosTheta*sCosTheta + 2.0);
    const double probabilityB = 0.5*
    (
        1.0 + sCosTheta*
        (
            sCosTheta - std::sqrt(sCosTheta*sCosTheta + 2.0)
        )
    );
    const double randomScaling =
        sCosTheta < -3.0 ? std::abs(sCosTheta) + 1.0 : 3.0;
    for (Foam::label parceli = 0; parceli < parcelCount; ++parceli)
    {
        const double openIntervalScale = 1.0 - 2.0e-12;
        const double positionTheta = theta
            + openIntervalScale*gate3c::angularWidth
             *(cloud.rndGen().sample01<Foam::scalar>() - 0.5);
        const double positionRadius = radius
            - 1.0e-7*gate3c::kineticRadialWidth;
        Foam::point position
        (
            positionRadius*std::cos(positionTheta),
            positionRadius*std::sin(positionTheta),
            0.0
        );
        position.z() = openIntervalScale*gate3c::kineticSpan
            *(cloud.rndGen().sample01<Foam::scalar>() - 0.5);

        double probability = -1.0;
        double normalVelocity = 0.0;
        int attempts = 0;
        do
        {
            const double thermalCandidate = randomScaling*
                (2.0*cloud.rndGen().sample01<Foam::scalar>() - 1.0);
            normalVelocity = thermalCandidate + sCosTheta;
            probability = normalVelocity < 0.0
                ? -1.0
                : 2.0*normalVelocity/probabilityA
                 *std::exp
                 (
                    probabilityB - thermalCandidate*thermalCandidate
                 );
            ++attempts;
        }
        while
        (
            probability < cloud.rndGen().sample01<Foam::scalar>()
         && attempts < 100000
        );
        if (attempts >= 100000)
        {
            return -1;
        }
        const Foam::vector velocity =
            std::sqrt(boltzmann*state.temperature/moleculeMass)
           *(
                cloud.rndGen().GaussNormal<Foam::scalar>()*t1
              + cloud.rndGen().GaussNormal<Foam::scalar>()*t2
            )
          + (t1 & reservoirVelocity)*t1
          + (t2 & reservoirVelocity)*t2
          + mostProbableSpeed*normalVelocity*inwardNormal;
        cloud.addNewParcel(position, ownerCell, velocity, 0.0, 0);
    }
    return parcelCount;
}

bool updateDynamicParticleDomain
(
    Foam::dsmcCloud& cloud,
    mui::uniface3d& interface,
    const int couplingStep,
    std::vector<double>& accumulators,
    std::vector<int>& liveLayers,
    const std::vector<int>& cellPoint,
    const std::vector<int>& cellLayer,
    const std::vector<Foam::label>& pointLayerToCell,
    Foam::label& reservoirInserted,
    Foam::label& transitionSeeded,
    Foam::label& removed,
    Foam::label& activatedCells,
    Foam::label& deactivatedCells,
    Foam::label& retainedIdentities,
    Foam::label& layerChanges,
    Foam::label& activeCells,
    double& activationZ
)
{
    std::vector<gate3c::State> states(gate3c::angularCells);
    std::vector<int> requestedLayers(gate3c::angularCells, -1);
    for (int point = 0; point < gate3c::angularCells; ++point)
    {
        states[point] = gate3c::fetchState
        (
            interface, gate3c::transportPoint(point), couplingStep
        );
        requestedLayers[point] = gate3e::fetchActiveLayers
        (
            interface, gate3c::transportPoint(point), couplingStep
        );
        if
        (
            !states[point].physical()
         || requestedLayers[point] < muiFoam::minimumContinuumLayers
         || requestedLayers[point] > muiFoam::maximumContinuumLayers
        )
        {
            return false;
        }
    }

    std::vector<bool> newlyActivated(cloud.mesh().nCells(), false);
    std::vector<bool> deactivated(cloud.mesh().nCells(), false);
    std::vector<bool> retained(cloud.mesh().nCells(), false);
    activeCells = 0;
    forAll(cellPoint, celli)
    {
        const bool oldActive = dynamicCellActive
        (
            celli, liveLayers, cellPoint, cellLayer
        );
        const bool newActive = dynamicCellActive
        (
            celli, requestedLayers, cellPoint, cellLayer
        );
        newlyActivated[celli] = newActive && !oldActive;
        deactivated[celli] = oldActive && !newActive;
        retained[celli] = oldActive && newActive;
        activatedCells += newlyActivated[celli] ? 1 : 0;
        deactivatedCells += deactivated[celli] ? 1 : 0;
        activeCells += newActive ? 1 : 0;
    }

    std::set<ParticleId> retainedBefore;
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        if (retained[parcel.cell()])
        {
            retainedBefore.insert
            (
                ParticleId(parcel.origProc(), parcel.origId())
            );
        }
    }

    for
    (
        Foam::dsmcCloud::iterator iter = cloud.begin();
        iter != cloud.end();
    )
    {
        Foam::dsmcParcel& parcel = iter();
        ++iter;
        if
        (
            newlyActivated[parcel.cell()]
         || !dynamicCellActive
            (
                parcel.cell(), requestedLayers, cellPoint, cellLayer
            )
        )
        {
            cloud.deleteParticle(parcel);
            ++removed;
        }
    }

    forAll(newlyActivated, celli)
    {
        if (newlyActivated[celli])
        {
            transitionSeeded += seedDynamicCell
            (
                cloud, celli, states[cellPoint[celli]]
            );
        }
    }
    activationZ = auditDynamicActivation
    (
        cloud, newlyActivated, states, cellPoint
    );
    if (!std::isfinite(activationZ) || activationZ > 1.0)
    {
        return false;
    }

    std::set<ParticleId> retainedAfter;
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        if (retained[parcel.cell()])
        {
            retainedAfter.insert
            (
                ParticleId(parcel.origProc(), parcel.origId())
            );
        }
    }
    if (retainedBefore != retainedAfter)
    {
        return false;
    }
    retainedIdentities += retainedAfter.size();
    for (int point = 0; point < gate3c::angularCells; ++point)
    {
        if (liveLayers[point] != requestedLayers[point])
        {
            ++layerChanges;
        }
        liveLayers[point] = requestedLayers[point];
        const int outerLayer =
            muiFoam::activeKineticLayers(liveLayers[point]) - 1;
        const Foam::label ownerCell = pointLayerToCell
        [
            point*muiFoam::kineticMeshLayers + outerLayer
        ];
        const Foam::label inserted = injectDynamicReservoirPoint
        (
            cloud, states[point], point, liveLayers[point], ownerCell,
            accumulators[point]
        );
        if (inserted < 0)
        {
            return false;
        }
        reservoirInserted += inserted;
    }
    return true;
}

Foam::label removeInactiveDynamicParcels
(
    Foam::dsmcCloud& cloud,
    const std::vector<int>& liveLayers,
    const std::vector<int>& cellPoint,
    const std::vector<int>& cellLayer
)
{
    Foam::label removed = 0;
    for
    (
        Foam::dsmcCloud::iterator iter = cloud.begin();
        iter != cloud.end();
    )
    {
        Foam::dsmcParcel& parcel = iter();
        ++iter;
        if
        (
            !dynamicCellActive
            (
                parcel.cell(), liveLayers, cellPoint, cellLayer
            )
        )
        {
            cloud.deleteParticle(parcel);
            ++removed;
        }
    }
    return removed;
}

Foam::label countInactiveDynamicParcels
(
    const Foam::dsmcCloud& cloud,
    const std::vector<int>& liveLayers,
    const std::vector<int>& cellPoint,
    const std::vector<int>& cellLayer
)
{
    Foam::label inactive = 0;
    for
    (
        Foam::dsmcCloud::const_iterator iter = cloud.cbegin();
        iter != cloud.cend();
        ++iter
    )
    {
        const Foam::dsmcParcel& parcel = iter();
        inactive += dynamicCellActive
        (
            parcel.cell(), liveLayers, cellPoint, cellLayer
        ) ? 0 : 1;
    }
    return inactive;
}
#endif

#ifdef GATE3E_LIVE
bool accumulateLiveFeedback
(
    const Foam::dsmcCloud& cloud,
    const Foam::label cylinderPatch,
    std::vector<double>& heat,
    std::vector<double>& forceX,
    std::vector<double>& forceY
)
{
    const Foam::polyPatch& cylinder =
        cloud.mesh().boundaryMesh()[cylinderPatch];
    const Foam::fvPatchScalarField& heatFlux =
        cloud.q().boundaryField()[cylinderPatch];
    const Foam::fvPatchVectorField& forceDensity =
        cloud.fD().boundaryField()[cylinderPatch];
    std::vector<bool> seen(gate3c::angularCells, false);
    forAll(cylinder, facei)
    {
        const Foam::point centre = cylinder.faceCentres()[facei];
        const int pointIndex = gate3c::pointIndex(centre.x(), centre.y());
        if
        (
            pointIndex < 0
         || seen[pointIndex]
         || !std::isfinite(heatFlux[facei])
         || !std::isfinite(forceDensity[facei].x())
         || !std::isfinite(forceDensity[facei].y())
        )
        {
            return false;
        }
        seen[pointIndex] = true;
        heat[pointIndex] += heatFlux[facei];
        forceX[pointIndex] += forceDensity[facei].x();
        forceY[pointIndex] += forceDensity[facei].y();
    }
    return cylinder.size() == gate3c::angularCells
        && std::find(seen.begin(), seen.end(), false) == seen.end();
}

bool pushLiveFeedback
(
    const Foam::dsmcCloud& cloud,
    const Foam::label cylinderPatch,
    mui::uniface3d& interface,
    const int couplingStep,
    const int sampleCount,
    const std::vector<double>& heat,
    const std::vector<double>& forceX,
    const std::vector<double>& forceY,
    double& checksum
)
{
    if (sampleCount != gate3e::samplesPerWindow)
    {
        return false;
    }
    const Foam::polyPatch& cylinder =
        cloud.mesh().boundaryMesh()[cylinderPatch];
    const Foam::scalarField& areas = cylinder.magFaceAreas();
    const double duration =
        gate3e::windowSteps*cloud.mesh().time().deltaTValue();
    std::vector<bool> seen(gate3c::angularCells, false);
    checksum = 0.0;
    forAll(cylinder, facei)
    {
        const Foam::point centre = cylinder.faceCentres()[facei];
        const int pointIndex = gate3c::pointIndex(centre.x(), centre.y());
        if
        (
            pointIndex < 0
         || seen[pointIndex]
         || !std::isfinite(areas[facei])
         || areas[facei] <= 0.0
        )
        {
            return false;
        }
        seen[pointIndex] = true;
        gate3e::Feedback feedback;
        feedback.mass = 0.0;
        feedback.momentumX = forceX[pointIndex]/sampleCount
            *areas[facei]*duration;
        feedback.momentumY = forceY[pointIndex]/sampleCount
            *areas[facei]*duration;
        feedback.momentumZ = 0.0;
        feedback.energy = heat[pointIndex]/sampleCount
            *areas[facei]*duration;
        feedback.samples = sampleCount;
        if (!feedback.physical())
        {
            return false;
        }
        gate3e::pushFeedback
        (
            interface,
            gate3c::transportPoint(pointIndex),
            feedback
        );
        checksum += std::abs(feedback.momentumX)
            + std::abs(feedback.momentumY)
            + std::abs(feedback.energy);
    }
    return std::find(seen.begin(), seen.end(), false) == seen.end();
}
#endif

bool writeWallSample
(
    const Foam::dsmcCloud& cloud,
    const Foam::label cylinderPatch,
    const std::string& role,
    const int couplingStep
)
{
    const Foam::polyPatch& cylinder =
        cloud.mesh().boundaryMesh()[cylinderPatch];
    const Foam::fvPatchScalarField& heatFlux =
        cloud.q().boundaryField()[cylinderPatch];
    const Foam::fvPatchVectorField& forceDensity =
        cloud.fD().boundaryField()[cylinderPatch];
    const Foam::scalarField& areas = cylinder.magFaceAreas();

    forAll(cylinder, facei)
    {
        const Foam::point centre = cylinder.faceCentres()[facei];
        double theta = std::atan2(centre.y(), centre.x());
        if (theta < 0.0)
        {
            theta += 2.0*gate3c::pi;
        }
        const double q = heatFlux[facei];
        const double drag = forceDensity[facei].x();
        const double lift = forceDensity[facei].y();
        if
        (
            !std::isfinite(q)
         || !std::isfinite(drag)
         || !std::isfinite(lift)
         || !std::isfinite(areas[facei])
         || areas[facei] <= 0.0
        )
        {
            Foam::Info<< "GATE3C_FAIL role=" << role.c_str()
                      << " reason=nonfinite_wall_observable"
                      << " step=" << couplingStep
                      << " face=" << facei << Foam::endl;
            return false;
        }
        Foam::Info<< "GATE3C_WALL"
                  << " role=" << role.c_str()
                  << " step=" << couplingStep
                  << " face=" << facei
                  << " theta=" << theta
                  << " area=" << areas[facei]
                  << " q=" << q
                  << " drag=" << drag
                  << " lift=" << lift << Foam::endl;
    }
    return true;
}

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Gate 3C full-reference or fixed-interface MUI DSMC cylinder run"
    );

    #define NO_CONTROL
    #include "postProcess.H"
    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"
    #include "createFields.H"

    const char* roleValue = std::getenv("GATE3C_ROLE");
    const std::string role = roleValue == nullptr ? "" : roleValue;
#ifdef GATE3E_LIVE
    const bool hybrid = role == "live";
    const bool reference = false;
#else
    const bool hybrid = role == "hybrid";
    const bool reference = role == "reference";
#endif
    if (!hybrid && !reference)
    {
        Foam::Info<< "GATE3C_FAIL role=unknown reason=GATE3C_ROLE"
                  << Foam::endl;
        return 2;
    }

    const Foam::label cylinderPatch =
        mesh.boundaryMesh().findPatchID("cylinder");
    if (cylinderPatch < 0 || dsmc.typeIdList().size() != 1 || dsmc.size() == 0)
    {
        Foam::Info<< "GATE3C_FAIL role=" << role.c_str()
                  << " reason=invalid_case_or_cloud" << Foam::endl;
        return 2;
    }

    std::unique_ptr<mui::uniface3d> interface;
    std::vector<double> accumulators(gate3c::angularCells, 0.0);
    if (hybrid)
    {
#ifdef GATE3E_LIVE
        interface.reset(new mui::uniface3d(liveDsmcUri));
#else
        interface.reset(new mui::uniface3d("mpi://dsmc/gate3c"));
#endif
    }

    int couplingStep = 0;
    Foam::label totalInserted = 0;
#ifdef GATE3E_LIVE
    int feedbackWindows = 0;
    int feedbackSamples = 0;
    int liveLayerChanges = 0;
    std::vector<int> liveLayers(gate3c::angularCells, 6);
    std::vector<double> heat(gate3c::angularCells, 0.0);
    std::vector<double> forceX(gate3c::angularCells, 0.0);
    std::vector<double> forceY(gate3c::angularCells, 0.0);
    double maximumFeedbackChecksum = 0.0;
#ifdef GATE3F_DYNAMIC
    const Foam::label initialParcels = dsmc.size();
    Foam::label totalTransitionSeeded = 0;
    Foam::label totalDynamicRemoved = 0;
    Foam::label dynamicActivatedCells = 0;
    Foam::label dynamicDeactivatedCells = 0;
    Foam::label retainedIdentities = 0;
    Foam::label currentActiveCells = 0;
    Foam::label maximumInactiveParcels = 0;
    long long maximumOwnershipBalanceError = 0;
    double maximumActivationZ = 0.0;
    std::vector<int> cellPoint;
    std::vector<int> cellLayer;
    std::vector<Foam::label> pointLayerToCell;
    if
    (
        !buildDynamicAddressing
        (
            mesh, cellPoint, cellLayer, pointLayerToCell
        )
    )
    {
        Foam::Info<< "GATE3F_FAIL role=dsmc reason=cell_addressing"
                  << Foam::endl;
        return 2;
    }
#endif
    while (couplingStep < gate3e::kineticSteps && runTime.loop())
#else
    while (runTime.loop())
#endif
    {
        ++couplingStep;
        Foam::Info<< "Time = " << runTime.timeName() << Foam::nl << Foam::endl;
        if (hybrid)
        {
#ifdef GATE3F_DYNAMIC
            double activationZ = 0.0;
            if
            (
                !updateDynamicParticleDomain
                (
                    dsmc, *interface, couplingStep, accumulators,
                    liveLayers, cellPoint, cellLayer, pointLayerToCell,
                    totalInserted, totalTransitionSeeded,
                    totalDynamicRemoved, dynamicActivatedCells,
                    dynamicDeactivatedCells, retainedIdentities,
                    liveLayerChanges, currentActiveCells, activationZ
                )
            )
            {
                Foam::Info<< "GATE3F_FAIL role=dsmc"
                          << " reason=dynamic_domain_transition"
                          << " step=" << couplingStep
                          << " max_overlap_z=" << activationZ << Foam::endl;
                return 2;
            }
            maximumActivationZ = std::max(maximumActivationZ, activationZ);
#else
            const Foam::label inserted = injectMappedReservoir
            (
                dsmc,
                *interface,
                couplingStep,
                accumulators
#ifdef GATE3E_LIVE
                ,
                liveLayers,
                liveLayerChanges
#endif
            );
            if (inserted < 0)
            {
                return 2;
            }
            totalInserted += inserted;
#endif
        }

        dsmc.evolve();
#ifdef GATE3F_DYNAMIC
        totalDynamicRemoved += removeInactiveDynamicParcels
        (
            dsmc, liveLayers, cellPoint, cellLayer
        );
        const Foam::label inactiveParcels = countInactiveDynamicParcels
        (
            dsmc, liveLayers, cellPoint, cellLayer
        );
        maximumInactiveParcels = std::max
        (
            maximumInactiveParcels, inactiveParcels
        );
        muiFoam::ParticleOwnershipLedger ownershipLedger;
        ownershipLedger.initialParcels = initialParcels;
        ownershipLedger.reservoirInserted = totalInserted;
        ownershipLedger.transitionSeeded = totalTransitionSeeded;
        ownershipLedger.removed = totalDynamicRemoved;
        ownershipLedger.finalParcels = dsmc.size();
        const long long ownershipError =
            muiFoam::particleOwnershipBalanceError(ownershipLedger);
        maximumOwnershipBalanceError = std::max
        (
            maximumOwnershipBalanceError, ownershipError
        );
        if (inactiveParcels != 0 || ownershipError != 0)
        {
            Foam::Info<< "GATE3F_FAIL role=dsmc reason=ownership_ledger"
                      << " step=" << couplingStep
                      << " inactive_parcels=" << inactiveParcels
                      << " balance_error=" << ownershipError << Foam::endl;
            return 2;
        }
#endif
#ifdef GATE3E_LIVE
        if (couplingStep % gate3e::sampleStride == 0)
        {
            if (!accumulateLiveFeedback
                (
                    dsmc, cylinderPatch, heat, forceX, forceY
                ))
            {
                Foam::Info<< liveGateLabel
                          << "_FAIL role=dsmc reason=wall_sample"
                          << " step=" << couplingStep << Foam::endl;
                return 2;
            }
            ++feedbackSamples;
        }
        gate3c::pushAcknowledgement(*interface, couplingStep);
        if (couplingStep % gate3e::windowSteps == 0)
        {
            double checksum = 0.0;
            if (!pushLiveFeedback
                (
                    dsmc, cylinderPatch, *interface, couplingStep,
                    feedbackSamples, heat, forceX, forceY, checksum
                ))
            {
                Foam::Info<< liveGateLabel
                          << "_FAIL role=dsmc reason=feedback_window"
                          << " step=" << couplingStep
                          << " samples=" << feedbackSamples << Foam::endl;
                return 2;
            }
            interface->commit(couplingStep);
            maximumFeedbackChecksum = std::max
            (
                maximumFeedbackChecksum, checksum
            );
            ++feedbackWindows;
            Foam::Info<< liveGateLabel << "_WINDOW role=dsmc"
                      << " window=" << feedbackWindows - 1
                      << " step=" << couplingStep
                      << " samples=" << feedbackSamples
                      << " flux_checksum=" << checksum
                      << " active_layer_changes=" << liveLayerChanges
#ifdef GATE3F_DYNAMIC
                      << " active_cells=" << currentActiveCells
                      << " activated_cells=" << dynamicActivatedCells
                      << " deactivated_cells=" << dynamicDeactivatedCells
                      << " seeded_parcels=" << totalTransitionSeeded
                      << " removed_parcels=" << totalDynamicRemoved
                      << " inactive_parcels=" << maximumInactiveParcels
                      << " ownership_balance_error="
                      << maximumOwnershipBalanceError
                      << " max_overlap_z=" << maximumActivationZ
#endif
                      << Foam::endl;
            std::fill(heat.begin(), heat.end(), 0.0);
            std::fill(forceX.begin(), forceX.end(), 0.0);
            std::fill(forceY.begin(), forceY.end(), 0.0);
            feedbackSamples = 0;
        }
        else
        {
            interface->commit(couplingStep);
        }
#else
        if
        (
            couplingStep >= gate3c::sampleStartStep
         && (couplingStep - gate3c::sampleStartStep)
            % gate3c::sampleStride == 0
         && !writeWallSample(dsmc, cylinderPatch, role, couplingStep)
        )
        {
            return 2;
        }
#endif
        if (couplingStep % 100 == 0)
        {
            Foam::Info<< "GATE3C_PROGRESS role=" << role.c_str()
                      << " step=" << couplingStep
                      << " parcels=" << dsmc.size()
                      << " inserted=" << totalInserted << Foam::endl;
        }
        runTime.write();
    }

#ifdef GATE3E_LIVE
#ifdef GATE3F_DYNAMIC
    const bool pass =
        couplingStep == gate3e::kineticSteps
     && feedbackWindows == gate3e::couplingWindows
     && feedbackSamples == 0
     && liveLayerChanges > 0
     && dynamicActivatedCells > 0
     && dynamicDeactivatedCells > 0
     && totalTransitionSeeded > 0
     && totalDynamicRemoved > 0
     && retainedIdentities > 0
     && maximumInactiveParcels == 0
     && maximumOwnershipBalanceError == 0
     && maximumActivationZ <= 1.0
     && maximumFeedbackChecksum > 0.0;
    Foam::Info<< (pass ? "GATE3F_PASS" : "GATE3F_FAIL")
              << " role=dsmc_live"
              << " steps=" << couplingStep
              << " windows=" << feedbackWindows
              << " final_parcels=" << dsmc.size()
              << " inserted=" << totalInserted
              << " active_layer_changes=" << liveLayerChanges
              << " max_flux_checksum=" << maximumFeedbackChecksum
              << " dynamic_activated_cells=" << dynamicActivatedCells
              << " deactivated_cells=" << dynamicDeactivatedCells
              << " seeded_parcels=" << totalTransitionSeeded
              << " removed_parcels=" << totalDynamicRemoved
              << " retained_identities=" << retainedIdentities
              << " inactive_parcels=" << maximumInactiveParcels
              << " ownership_balance_error="
              << maximumOwnershipBalanceError
              << " max_overlap_z=" << maximumActivationZ
              << Foam::endl;
#else
    const bool pass =
        couplingStep == gate3e::kineticSteps
     && feedbackWindows == gate3e::couplingWindows
     && feedbackSamples == 0
     && liveLayerChanges > 0
     && maximumFeedbackChecksum > 0.0;
    Foam::Info<< liveGateLabel << (pass ? "_PASS" : "_FAIL")
              << " role=dsmc_live"
              << " steps=" << couplingStep
              << " windows=" << feedbackWindows
              << " final_parcels=" << dsmc.size()
              << " inserted=" << totalInserted
              << " active_layer_changes=" << liveLayerChanges
              << " max_flux_checksum=" << maximumFeedbackChecksum
              << Foam::endl;
#endif
#else
    const bool pass = couplingStep == gate3c::kineticSteps;
    Foam::Info<< (pass ? "GATE3C_PASS" : "GATE3C_FAIL")
              << " role=" << role.c_str()
              << " steps=" << couplingStep
              << " final_parcels=" << dsmc.size()
              << " inserted=" << totalInserted << Foam::endl;
#endif
    return pass ? 0 : 2;
}
