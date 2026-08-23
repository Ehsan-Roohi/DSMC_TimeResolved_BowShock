// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"
#include "Gate1CMui.H"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <string>
#include <vector>

namespace
{

constexpr double boltzmann = 1.380649e-23;

bool isMappedPatch(const Foam::word& name)
{
    return name == "inlet" || name == "interface" || name == "outlet";
}

Foam::vector tangent(const Foam::vector& inwardNormal)
{
    Foam::vector reference(0, 0, 1);
    if (std::abs(inwardNormal & reference) > 0.9)
    {
        reference = Foam::vector(0, 1, 0);
    }
    Foam::vector result = inwardNormal ^ reference;
    result /= Foam::mag(result);
    return result;
}

Foam::label injectMappedReservoir
(
    Foam::dsmcCloud& cloud,
    mui::uniface3d& interface,
    const int couplingStep,
    std::vector<double>& accumulators
)
{
    const Foam::fvMesh& mesh = cloud.mesh();
    const double deltaT = mesh.time().deltaTValue();
    const double moleculeMass = cloud.constProps(0).mass();
    const double equivalentParticles = cloud.nParticle();
    Foam::label inserted = 0;
    Foam::label mappedFaces = 0;
    std::vector<bool> mappedPointSeen(gate1c::couplingPointCount, false);

    forAll(mesh.boundaryMesh(), patchi)
    {
        const Foam::polyPatch& patch = mesh.boundaryMesh()[patchi];
        if (!isMappedPatch(patch.name()))
        {
            continue;
        }

        const Foam::pointField::subField faceCentres = patch.faceCentres();
        const Foam::vectorField::subField faceAreas = patch.faceAreas();
        const Foam::scalarField& faceAreaMagnitudes = patch.magFaceAreas();

        forAll(patch, facei)
        {
            const Foam::point& faceCentre = faceCentres[facei];
            const int pointIndex = gate1c::pointIndex
            (
                faceCentre.x(),
                faceCentre.y()
            );
            if (pointIndex < 0 || pointIndex >= gate1c::couplingPointCount)
            {
                Foam::Info<< "GATE1C_FAIL role=hybrid"
                          << " reason=unmapped_boundary_face"
                          << " patch=" << patch.name()
                          << " centre=" << faceCentre << Foam::endl;
                return -1;
            }
            if (mappedPointSeen[pointIndex])
            {
                Foam::Info<< "GATE1C_FAIL role=hybrid"
                          << " reason=duplicate_mapped_point"
                          << " point=" << pointIndex
                          << " patch=" << patch.name()
                          << " centre=" << faceCentre << Foam::endl;
                return -1;
            }
            mappedPointSeen[pointIndex] = true;

            const gate1c::State state = gate1c::fetchState
            (
                interface,
                gate1c::transportPoint(pointIndex),
                couplingStep
            );
            if (!state.physical())
            {
                Foam::Info<< "GATE1C_FAIL role=hybrid"
                          << " reason=nonphysical_mapped_state"
                          << " point=" << pointIndex
                          << " step=" << couplingStep << Foam::endl;
                return -1;
            }

            const Foam::vector inwardNormal =
                -faceAreas[facei]/faceAreaMagnitudes[facei];
            const Foam::vector t1 = tangent(inwardNormal);
            const Foam::vector t2 = inwardNormal ^ t1;
            const Foam::vector reservoirVelocity
            (
                state.ux,
                state.uy,
                state.uz
            );
            const double mostProbableSpeed = std::sqrt
            (
                2.0*boltzmann*state.temperature/moleculeMass
            );
            const double sCosTheta =
                (reservoirVelocity & inwardNormal)/mostProbableSpeed;
            const double sqrtPi = std::sqrt(std::acos(-1.0));
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
                    sCosTheta
                  - std::sqrt(sCosTheta*sCosTheta + 2.0)
                )
            );
            const double randomScaling =
                sCosTheta < -3.0 ? std::abs(sCosTheta) + 1.0 : 3.0;

            const Foam::label globalFace = patch.start() + facei;
            const Foam::label celli = mesh.faceOwner()[globalFace];
            for (Foam::label parceli = 0; parceli < parcelCount; ++parceli)
            {
                Foam::point position(faceCentre);
                const double openIntervalScale = 1.0 - 2.0e-12;
                if (patch.name() == "interface")
                {
                    position.x() += openIntervalScale*gate1c::kineticDx*
                        (cloud.rndGen().sample01<Foam::scalar>() - 0.5);
                }
                else
                {
                    position.y() += openIntervalScale*gate1c::kineticDy*
                        (cloud.rndGen().sample01<Foam::scalar>() - 0.5);
                }
                position.z() = openIntervalScale*gate1c::kineticSpan*
                    (cloud.rndGen().sample01<Foam::scalar>() - 0.5);
                position += 1.0e-7*gate1c::kineticDy*inwardNormal;

                double probability = -1.0;
                double normalVelocity = 0.0;
                int attempts = 0;
                do
                {
                    const double thermalCandidate = randomScaling*
                        (
                            2.0*cloud.rndGen().sample01<Foam::scalar>()
                          - 1.0
                        );
                    normalVelocity = thermalCandidate + sCosTheta;
                    probability = normalVelocity < 0.0
                        ? -1.0
                        : 2.0*normalVelocity/probabilityA
                         *std::exp
                         (
                             probabilityB
                           - thermalCandidate*thermalCandidate
                         );
                    ++attempts;
                }
                while
                (
                    probability
                  < cloud.rndGen().sample01<Foam::scalar>()
                 && attempts < 100000
                );

                if (attempts >= 100000)
                {
                    Foam::Info<< "GATE1C_FAIL role=hybrid"
                              << " reason=inflow_velocity_rejection"
                              << Foam::endl;
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
            ++mappedFaces;
        }
    }

    if
    (
        mappedFaces != gate1c::couplingPointCount
     || std::find(mappedPointSeen.begin(), mappedPointSeen.end(), false)
        != mappedPointSeen.end()
    )
    {
        Foam::Info<< "GATE1C_FAIL role=hybrid"
                  << " reason=mapped_face_count"
                  << " expected=" << gate1c::couplingPointCount
                  << " actual=" << mappedFaces << Foam::endl;
        return -1;
    }

    gate1c::pushAcknowledgement(interface, couplingStep);
    interface.commit(couplingStep);
    return inserted;
}

bool writeWallSample
(
    const Foam::dsmcCloud& cloud,
    const Foam::label platePatch,
    const std::string& role,
    const int couplingStep
)
{
    const Foam::polyPatch& plate = cloud.mesh().boundaryMesh()[platePatch];
    const Foam::fvPatchScalarField& heatFlux =
        cloud.q().boundaryField()[platePatch];
    const Foam::fvPatchVectorField& forceDensity =
        cloud.fD().boundaryField()[platePatch];

    forAll(plate, facei)
    {
        const double q = heatFlux[facei];
        const double tau = forceDensity[facei].x();
        if (!std::isfinite(q) || !std::isfinite(tau))
        {
            Foam::Info<< "GATE1C_FAIL role=" << role
                      << " reason=nonfinite_wall_observable"
                      << " step=" << couplingStep
                      << " face=" << facei << Foam::endl;
            return false;
        }

        Foam::Info<< "GATE1C_WALL"
                  << " role=" << role
                  << " step=" << couplingStep
                  << " face=" << facei
                  << " x=" << plate.faceCentres()[facei].x()
                  << " q=" << q
                  << " tau=" << tau << Foam::endl;
    }
    return true;
}

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Gate 1C full-reference or fixed-interface MUI DSMC flat-plate run"
    );

    #define NO_CONTROL
    #include "postProcess.H"
    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"
    #include "createFields.H"

    const char* roleValue = std::getenv("GATE1C_ROLE");
    const std::string role = roleValue == nullptr ? "" : roleValue;
    const bool hybrid = role == "hybrid";
    const bool reference = role == "reference";
    if (!hybrid && !reference)
    {
        Foam::Info<< "GATE1C_FAIL role=unknown reason=GATE1C_ROLE"
                  << Foam::endl;
        return 2;
    }

    const Foam::label platePatch = mesh.boundaryMesh().findPatchID("plate");
    if (platePatch < 0 || dsmc.typeIdList().size() != 1 || dsmc.size() == 0)
    {
        Foam::Info<< "GATE1C_FAIL role=" << role
                  << " reason=invalid_case_or_cloud" << Foam::endl;
        return 2;
    }

    std::unique_ptr<mui::uniface3d> interface;
    std::vector<double> accumulators(gate1c::couplingPointCount, 0.0);
    if (hybrid)
    {
        interface.reset(new mui::uniface3d("mpi://dsmc/gate1c"));
    }

    int couplingStep = 0;
    Foam::label totalInserted = 0;
    while (runTime.loop())
    {
        ++couplingStep;
        Foam::Info<< "Time = " << runTime.timeName() << Foam::nl << Foam::endl;

        if (hybrid)
        {
            const Foam::label inserted = injectMappedReservoir
            (
                dsmc,
                *interface,
                couplingStep,
                accumulators
            );
            if (inserted < 0)
            {
                return 2;
            }
            totalInserted += inserted;
        }

        dsmc.evolve();

        if
        (
            couplingStep >= gate1c::sampleStartStep
         && (couplingStep - gate1c::sampleStartStep)
            % gate1c::sampleStride == 0
         && !writeWallSample(dsmc, platePatch, role, couplingStep)
        )
        {
            return 2;
        }

        if (couplingStep % 100 == 0)
        {
            Foam::Info<< "GATE1C_PROGRESS role=" << role
                      << " step=" << couplingStep
                      << " parcels=" << dsmc.size()
                      << " inserted=" << totalInserted << Foam::endl;
        }
        runTime.write();
    }

    const bool pass = couplingStep == gate1c::kineticSteps;
    Foam::Info<< (pass ? "GATE1C_PASS" : "GATE1C_FAIL")
              << " role=" << role
              << " steps=" << couplingStep
              << " final_parcels=" << dsmc.size()
              << " inserted=" << totalInserted << Foam::endl;
    return pass ? 0 : 2;
}
