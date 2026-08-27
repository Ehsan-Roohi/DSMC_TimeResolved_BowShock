// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"
#ifdef GATE3E_LIVE
#include "Gate3EMui.H"
#else
#include "Gate3CMui.H"
#endif

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <memory>
#include <string>
#include <vector>

namespace
{

constexpr double boltzmann = 1.380649e-23;

Foam::vector tangent(const Foam::vector& inwardNormal)
{
    Foam::vector reference(0, 0, 1);
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
        interface.reset(new mui::uniface3d("mpi://dsmc/gate3e"));
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
    while (couplingStep < gate3e::kineticSteps && runTime.loop())
#else
    while (runTime.loop())
#endif
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
        }

        dsmc.evolve();
#ifdef GATE3E_LIVE
        if (couplingStep % gate3e::sampleStride == 0)
        {
            if (!accumulateLiveFeedback
                (
                    dsmc, cylinderPatch, heat, forceX, forceY
                ))
            {
                Foam::Info<< "GATE3E_FAIL role=dsmc reason=wall_sample"
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
                Foam::Info<< "GATE3E_FAIL role=dsmc reason=feedback_window"
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
            Foam::Info<< "GATE3E_WINDOW role=dsmc"
                      << " window=" << feedbackWindows - 1
                      << " step=" << couplingStep
                      << " samples=" << feedbackSamples
                      << " flux_checksum=" << checksum
                      << " active_layer_changes=" << liveLayerChanges
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
    const bool pass =
        couplingStep == gate3e::kineticSteps
     && feedbackWindows == gate3e::couplingWindows
     && feedbackSamples == 0
     && liveLayerChanges > 0
     && maximumFeedbackChecksum > 0.0;
    Foam::Info<< (pass ? "GATE3E_PASS" : "GATE3E_FAIL")
              << " role=dsmc_live"
              << " steps=" << couplingStep
              << " windows=" << feedbackWindows
              << " final_parcels=" << dsmc.size()
              << " inserted=" << totalInserted
              << " active_layer_changes=" << liveLayerChanges
              << " max_flux_checksum=" << maximumFeedbackChecksum
              << Foam::endl;
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
