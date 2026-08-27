// SPDX-License-Identifier: GPL-3.0-or-later
// Based on the OpenFOAM-v2312 rhoCentralFoam time loop.
#include "fvCFD.H"
#include "dynamicFvMesh.H"
#include "psiThermo.H"
#include "turbulentFluidThermoModel.H"
#include "fixedRhoFvPatchScalarField.H"
#include "directionInterpolate.H"
#include "localEulerDdtScheme.H"
#include "fvcSmooth.H"
#include "Gate1BMui.H"
#ifdef GATE3E_LIVE
#include "Gate3EMui.H"
#include "muiFoam/PhysicalFeedback.hpp"
#endif

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <string>
#include <vector>

namespace
{

const double conservationTolerance = 1.0e-10;
const double crossStateTolerance = 1.0e-3;

struct Conserved
{
    double mass;
    Foam::vector momentum;
    double energy;
};

Conserved continuumConserved
(
    const Foam::fvMesh& mesh,
    const Foam::volScalarField& rho,
    const Foam::volVectorField& rhoU,
    const Foam::volScalarField& rhoE
)
{
    Conserved totals;
    totals.mass = 0.0;
    totals.momentum = Foam::vector::zero;
    totals.energy = 0.0;

    forAll(mesh.V(), celli)
    {
        const double volume = mesh.V()[celli];
        totals.mass += rho[celli]*volume;
        totals.momentum += rhoU[celli]*volume;
        totals.energy += rhoE[celli]*volume;
    }
    return totals;
}

gate1b::State continuumState
(
    const Foam::fvMesh& mesh,
    const Foam::volScalarField& rho,
    const Foam::volVectorField& rhoU,
    const Foam::volScalarField& rhoE,
    const Foam::volScalarField& temperature,
    const Foam::volScalarField& pressure,
    const Foam::volVectorField& velocity
)
{
    const Conserved totals = continuumConserved(mesh, rho, rhoU, rhoE);
    double volume = 0.0;
    double temperatureVolume = 0.0;
    double physicalEnergy = 0.0;
    forAll(mesh.V(), celli)
    {
        volume += mesh.V()[celli];
        temperatureVolume += temperature[celli]*mesh.V()[celli];

        // rhoE uses OpenFOAM's thermodynamic reference energy and can be
        // negative near Tref.  MUI transports the reference-independent,
        // absolute monatomic translational plus bulk kinetic energy instead.
        physicalEnergy +=
        (
            1.5*pressure[celli]
          + 0.5*rho[celli]*Foam::magSqr(velocity[celli])
        )*mesh.V()[celli];
    }

    gate1b::State state;
    state.rho = totals.mass/volume;
    state.ux = totals.momentum.x()/totals.mass;
    state.uy = totals.momentum.y()/totals.mass;
    state.uz = totals.momentum.z()/totals.mass;
    state.temperature = temperatureVolume/volume;
    state.specificEnergy = physicalEnergy/totals.mass;
    return state;
}

double conservationError(const Conserved& current, const Conserved& initial)
{
    const double massError =
        std::abs(current.mass - initial.mass)/initial.mass;
    const double energyError =
        std::abs(current.energy - initial.energy)/std::abs(initial.energy);
    const double momentumScale = std::max
    (
        initial.mass,
        Foam::mag(initial.momentum)
    );
    const double momentumError =
        Foam::mag(current.momentum - initial.momentum)/momentumScale;
    return std::max(massError, std::max(energyError, momentumError));
}

#ifdef GATE3E_LIVE
constexpr double boltzmann = 1.380649e-23;
constexpr double argonGasConstant = 8.31446261815324e3/39.948;
constexpr double argonCv = 1.5*argonGasConstant;

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

double relativeDifference(const double actual, const double expected)
{
    return std::abs(actual - expected)/std::max
    (
        1.0, std::max(std::abs(actual), std::abs(expected))
    );
}
#endif

} // namespace

int main(int argc, char *argv[])
{
    Foam::argList::addNote
    (
        "Gate 1B rhoCentralFoam with live MUI state exchange and audit"
    );

    #define NO_CONTROL
    #include "postProcess.H"
    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createDynamicFvMesh.H"
    #include "createFields.H"
    #include "createFieldRefs.H"
    #include "createTimeControls.H"

    turbulence->validate();

    #include "readFluxScheme.H"

    const Foam::dimensionedScalar v_zero
    (
        Foam::dimVolume/Foam::dimTime,
        Foam::Zero
    );

    Foam::scalar CoNum = 0.0;
    Foam::scalar meanCoNum = 0.0;

    mui::uniface3d interface
    (
#ifdef GATE3E_LIVE
        "mpi://continuum/gate3e"
#else
        "mpi://continuum/gate1b"
#endif
    );
#ifdef GATE3E_LIVE
    const char* comparisonValue = std::getenv("GATE3E_COMPARISON");
    if (comparisonValue == nullptr)
    {
        Foam::Info<< "GATE3E_FAIL role=continuum reason=environment"
                  << Foam::endl;
        return 2;
    }
    std::vector<muiFoam::PhysicalWallSample> physicalSamples;
    try
    {
        physicalSamples = muiFoam::readGate3CComparison(comparisonValue);
    }
    catch (const std::exception& error)
    {
        Foam::Info<< "GATE3E_FAIL role=continuum reason=comparison"
                  << " detail=" << error.what() << Foam::endl;
        return 2;
    }
    const double heatScale = muiFoam::robustScale(physicalSamples, true);
    const double dragScale = muiFoam::robustScale(physicalSamples, false);
    std::vector<double> indicators(gate3c::angularCells, 0.0);
    for (int face = 0; face < gate3c::angularCells; ++face)
    {
        indicators[face] = muiFoam::physicalDiscrepancyIndicator
        (
            physicalSamples[face], heatScale, dragScale
        );
    }
    int couplingStep = 0;
    int completedWindows = 0;
    int adaptiveLayerChanges = 0;
    std::vector<int> previousLayers(gate3c::angularCells, 6);
    double maximumFeedbackConservationError = 0.0;
    double maximumVelocityChange = 0.0;
    double maximumTemperatureChange = 0.0;
    double minimumFeedbackScale = 1.0;
    Foam::Info<< "\nStarting Gate 3E live rhoCentralFoam/DSMC loop\n"
              << Foam::endl;
#else
    const Conserved initial = continuumConserved(mesh, rho, rhoU, rhoE);
    const gate1b::State initialState =
        continuumState(mesh, rho, rhoU, rhoE, T, p, U);

    Foam::Info<< "GATE1B_CONTINUUM_INITIAL"
              << " rho=" << initialState.rho
              << " U=(" << initialState.ux << ' ' << initialState.uy
              << ' ' << initialState.uz << ')'
              << " T=" << initialState.temperature
              << " physical_specific_energy=" << initialState.specificEnergy
              << " openfoam_reference_specific_energy="
              << initial.energy/initial.mass << Foam::endl;

    if (!initialState.physical())
    {
        Foam::Info<< "GATE1B_FAIL role=continuum reason=nonphysical_initial"
                  << Foam::endl;
        return 2;
    }

    gate1b::pushState(interface, "continuum_", initialState);
    interface.commit(0);
    const gate1b::State dsmcInitial =
        gate1b::fetchState(interface, "dsmc_", 0);
    if (!dsmcInitial.physical())
    {
        Foam::Info<< "GATE1B_FAIL role=continuum reason=dsmc_handshake"
                  << Foam::endl;
        return 2;
    }

    int couplingStep = 0;
    double maxConservationError = 0.0;
    double maxCrossStateError = 0.0;

    Foam::Info<< "\nStarting Gate 1B rhoCentralFoam time loop\n"
              << Foam::endl;
#endif

#ifdef GATE3E_LIVE
    while (couplingStep < gate3e::kineticSteps && runTime.run())
#else
    while (runTime.run())
#endif
    {
        #include "readTimeControls.H"

        if (!LTS)
        {
            #include "setDeltaT.H"
            ++runTime;
            mesh.update();
        }

        Foam::surfaceScalarField rho_pos(interpolate(rho, pos));
        Foam::surfaceScalarField rho_neg(interpolate(rho, neg));
        Foam::surfaceVectorField rhoU_pos(interpolate(rhoU, pos, U.name()));
        Foam::surfaceVectorField rhoU_neg(interpolate(rhoU, neg, U.name()));

        Foam::volScalarField rPsi("rPsi", 1.0/psi);
        Foam::surfaceScalarField rPsi_pos(interpolate(rPsi, pos, T.name()));
        Foam::surfaceScalarField rPsi_neg(interpolate(rPsi, neg, T.name()));
        Foam::surfaceScalarField e_pos(interpolate(e, pos, T.name()));
        Foam::surfaceScalarField e_neg(interpolate(e, neg, T.name()));
        Foam::surfaceVectorField U_pos("U_pos", rhoU_pos/rho_pos);
        Foam::surfaceVectorField U_neg("U_neg", rhoU_neg/rho_neg);
        Foam::surfaceScalarField p_pos("p_pos", rho_pos*rPsi_pos);
        Foam::surfaceScalarField p_neg("p_neg", rho_neg*rPsi_neg);

        Foam::surfaceScalarField phiv_pos("phiv_pos", U_pos & mesh.Sf());
        phiv_pos.setOriented(false);
        Foam::surfaceScalarField phiv_neg("phiv_neg", U_neg & mesh.Sf());
        phiv_neg.setOriented(false);

        if (mesh.moving())
        {
            Foam::surfaceScalarField meshPhi(mesh.phi());
            meshPhi.setOriented(false);
            phiv_pos -= meshPhi;
            phiv_neg -= meshPhi;
        }

        Foam::volScalarField c("c", sqrt(thermo.Cp()/thermo.Cv()*rPsi));
        Foam::surfaceScalarField cSf_pos
        (
            "cSf_pos",
            interpolate(c, pos, T.name())*mesh.magSf()
        );
        Foam::surfaceScalarField cSf_neg
        (
            "cSf_neg",
            interpolate(c, neg, T.name())*mesh.magSf()
        );

        Foam::surfaceScalarField ap
        (
            "ap",
            max(max(phiv_pos + cSf_pos, phiv_neg + cSf_neg), v_zero)
        );
        Foam::surfaceScalarField am
        (
            "am",
            min(min(phiv_pos - cSf_pos, phiv_neg - cSf_neg), v_zero)
        );
        Foam::surfaceScalarField a_pos("a_pos", ap/(ap - am));
        Foam::surfaceScalarField amaxSf("amaxSf", max(mag(am), mag(ap)));
        Foam::surfaceScalarField aSf("aSf", am*a_pos);

        if (fluxScheme == "Tadmor")
        {
            aSf = -0.5*amaxSf;
            a_pos = 0.5;
        }

        Foam::surfaceScalarField a_neg("a_neg", 1.0 - a_pos);
        phiv_pos *= a_pos;
        phiv_neg *= a_neg;
        Foam::surfaceScalarField aphiv_pos("aphiv_pos", phiv_pos - aSf);
        Foam::surfaceScalarField aphiv_neg("aphiv_neg", phiv_neg + aSf);
        amaxSf = max(mag(aphiv_pos), mag(aphiv_neg));

        #include "centralCourantNo.H"

        if (LTS)
        {
            #include "setRDeltaT.H"
            ++runTime;
        }

        Foam::Info<< "Time = " << runTime.timeName() << Foam::nl << Foam::endl;

        phi = aphiv_pos*rho_pos + aphiv_neg*rho_neg;
        Foam::surfaceVectorField phiU
        (
            aphiv_pos*rhoU_pos + aphiv_neg*rhoU_neg
        );
        phiU.setOriented(true);
        Foam::surfaceVectorField phiUp
        (
            phiU + (a_pos*p_pos + a_neg*p_neg)*mesh.Sf()
        );
        Foam::surfaceScalarField phiEp
        (
            "phiEp",
            aphiv_pos*(rho_pos*(e_pos + 0.5*magSqr(U_pos)) + p_pos)
          + aphiv_neg*(rho_neg*(e_neg + 0.5*magSqr(U_neg)) + p_neg)
          + aSf*p_pos - aSf*p_neg
        );

        if (mesh.moving())
        {
            Foam::surfaceScalarField meshPhi(mesh.phi());
            meshPhi.setOriented(false);
            phiEp += meshPhi*(a_pos*p_pos + a_neg*p_neg);
        }

        Foam::volScalarField muEff("muEff", turbulence->muEff());
        Foam::volTensorField tauMC
        (
            "tauMC",
            muEff*dev2(Foam::T(fvc::grad(U)))
        );

        solve(fvm::ddt(rho) + fvc::div(phi));
        solve(fvm::ddt(rhoU) + fvc::div(phiUp));

        U.ref() = rhoU()/rho();
        U.correctBoundaryConditions();
        rhoU.boundaryFieldRef() ==
            rho.boundaryField()*U.boundaryField();

        if (!inviscid)
        {
            solve
            (
                fvm::ddt(rho, U) - fvc::ddt(rho, U)
              - fvm::laplacian(muEff, U)
              - fvc::div(tauMC)
            );
            rhoU = rho*U;
        }

        Foam::surfaceScalarField sigmaDotU
        (
            "sigmaDotU",
            (
                fvc::interpolate(muEff)*mesh.magSf()*fvc::snGrad(U)
              + fvc::dotInterpolate(mesh.Sf(), tauMC)
            )
          & (a_pos*U_pos + a_neg*U_neg)
        );

        solve
        (
            fvm::ddt(rhoE)
          + fvc::div(phiEp)
          - fvc::div(sigmaDotU)
        );

        e = rhoE/rho - 0.5*magSqr(U);
        e.correctBoundaryConditions();
        thermo.correct();
        rhoE.boundaryFieldRef() ==
            rho.boundaryField()
           *(
                e.boundaryField()
              + 0.5*magSqr(U.boundaryField())
            );

        if (!inviscid)
        {
            solve
            (
                fvm::ddt(rho, e) - fvc::ddt(rho, e)
              - fvm::laplacian(turbulence->alphaEff(), e)
            );
            thermo.correct();
            rhoE = rho*(e + 0.5*magSqr(U));
        }

        p.ref() = rho()/psi();
        p.correctBoundaryConditions();
        rho.boundaryFieldRef() ==
            psi.boundaryField()*p.boundaryField();
        turbulence->correct();

#ifdef GATE3E_LIVE
        ++couplingStep;
        const int window = (couplingStep - 1)/gate3e::windowSteps;
        std::vector<Foam::label> targetCells(gate3c::angularCells, -1);
        for (int face = 0; face < gate3c::angularCells; ++face)
        {
            const int activeLayers = muiFoam::physicalLayersAtWindow
            (
                indicators[face], window
            );
            if (activeLayers != previousLayers[face])
            {
                previousLayers[face] = activeLayers;
                ++adaptiveLayerChanges;
            }
            const Foam::label celli = nearestCell
            (
                mesh,
                gate3e::continuumSamplePoint(face, activeLayers)
            );
            if (celli < 0 || T[celli] <= 0.0 || p[celli] <= 0.0)
            {
                Foam::Info<< "GATE3E_FAIL role=continuum"
                          << " reason=sample_cell face=" << face
                          << " step=" << couplingStep << Foam::endl;
                return 2;
            }
            targetCells[face] = celli;
            gate3c::State state;
            state.numberDensity = p[celli]/(boltzmann*T[celli]);
            state.ux = U[celli].x();
            state.uy = U[celli].y();
            state.uz = U[celli].z();
            state.temperature = T[celli];
            if (!state.physical())
            {
                Foam::Info<< "GATE3E_FAIL role=continuum"
                          << " reason=nonphysical_state face=" << face
                          << " step=" << couplingStep << Foam::endl;
                return 2;
            }
            gate3c::pushState
            (
                interface, gate3c::transportPoint(face), state
            );
            gate3e::pushActiveLayers
            (
                interface, gate3c::transportPoint(face), activeLayers
            );
        }
        interface.commit(couplingStep);
        const double acknowledgement = gate3c::fetchAcknowledgement
        (
            interface, couplingStep
        );
        if (std::abs(acknowledgement - couplingStep) > 1.0e-12)
        {
            Foam::Info<< "GATE3E_FAIL role=continuum reason=acknowledgement"
                      << " step=" << couplingStep
                      << " value=" << acknowledgement << Foam::endl;
            return 2;
        }

        if (couplingStep % gate3e::windowSteps == 0)
        {
            std::vector<gate3e::Feedback> feedback(gate3c::angularCells);
            double scale = 1.0;
            Foam::vector requestedMomentum = Foam::vector::zero;
            double requestedEnergy = 0.0;
            for (int face = 0; face < gate3c::angularCells; ++face)
            {
                feedback[face] = gate3e::fetchFeedback
                (
                    interface,
                    gate3c::transportPoint(face),
                    couplingStep
                );
                if (!feedback[face].physical())
                {
                    Foam::Info<< "GATE3E_FAIL role=continuum"
                              << " reason=feedback face=" << face
                              << " step=" << couplingStep << Foam::endl;
                    return 2;
                }
                const Foam::label celli = targetCells[face];
                const double density = rho[celli];
                const double volume = mesh.V()[celli];
                const Foam::vector packetMomentum
                (
                    feedback[face].momentumX,
                    feedback[face].momentumY,
                    feedback[face].momentumZ
                );
                const double velocityScale = std::max
                (
                    Foam::mag(U[celli]),
                    std::sqrt(argonGasConstant*T[celli])
                );
                const double momentumRatio = Foam::mag(packetMomentum)
                    /std::max(density*volume*velocityScale, Foam::VSMALL);
                const double energyRatio = std::abs(feedback[face].energy)
                    /std::max
                    (
                        density*volume*argonCv*T[celli], Foam::VSMALL
                    );
                const double ratio = std::max(momentumRatio, energyRatio);
                if (ratio > gate3e::maximumFractionalCorrection)
                {
                    scale = std::min
                    (
                        scale,
                        gate3e::maximumFractionalCorrection/ratio
                    );
                }
                requestedMomentum -= packetMomentum;
                requestedEnergy -= feedback[face].energy;
            }
            if (!std::isfinite(scale) || scale <= 0.0 || scale > 1.0)
            {
                Foam::Info<< "GATE3E_FAIL role=continuum reason=scale"
                          << " value=" << scale << Foam::endl;
                return 2;
            }

            Foam::vector appliedMomentum = Foam::vector::zero;
            double appliedEnergy = 0.0;
            double windowMaximumVelocityChange = 0.0;
            double windowMaximumTemperatureChange = 0.0;
            for (int face = 0; face < gate3c::angularCells; ++face)
            {
                const Foam::label celli = targetCells[face];
                const double density = rho[celli];
                const double volume = mesh.V()[celli];
                const Foam::vector oldVelocity = U[celli];
                const double oldTemperature = T[celli];
                const Foam::vector deltaMomentum = -scale*Foam::vector
                (
                    feedback[face].momentumX,
                    feedback[face].momentumY,
                    feedback[face].momentumZ
                );
                const double deltaEnergy = -scale*feedback[face].energy;
                const Foam::vector newVelocity = oldVelocity
                    + deltaMomentum/(density*volume);
                const double oldPhysicalEnergyDensity = density*
                (
                    argonCv*oldTemperature
                  + 0.5*Foam::magSqr(oldVelocity)
                );
                const double newPhysicalEnergyDensity =
                    oldPhysicalEnergyDensity + deltaEnergy/volume;
                const double newTemperature =
                (
                    newPhysicalEnergyDensity/density
                  - 0.5*Foam::magSqr(newVelocity)
                )/argonCv;
                if (!std::isfinite(newTemperature) || newTemperature <= 0.0)
                {
                    Foam::Info<< "GATE3E_FAIL role=continuum"
                              << " reason=corrected_state face=" << face
                              << " step=" << couplingStep << Foam::endl;
                    return 2;
                }
                U[celli] = newVelocity;
                T[celli] = newTemperature;
                e[celli] += argonCv*(newTemperature - oldTemperature);
                rhoU[celli] = density*newVelocity;
                rhoE[celli] = density*
                (
                    e[celli] + 0.5*Foam::magSqr(newVelocity)
                );
                appliedMomentum += deltaMomentum;
                appliedEnergy += deltaEnergy;
                windowMaximumVelocityChange = std::max
                (
                    windowMaximumVelocityChange,
                    Foam::mag(newVelocity - oldVelocity)
                );
                windowMaximumTemperatureChange = std::max
                (
                    windowMaximumTemperatureChange,
                    std::abs(newTemperature - oldTemperature)
                );
            }
            U.correctBoundaryConditions();
            e.correctBoundaryConditions();
            thermo.correct();
            rhoU.boundaryFieldRef() ==
                rho.boundaryField()*U.boundaryField();
            rhoE = rho*(e + 0.5*magSqr(U));
            p.ref() = rho()/psi();
            p.correctBoundaryConditions();
            rho.boundaryFieldRef() ==
                psi.boundaryField()*p.boundaryField();

            const Foam::vector expectedMomentum = scale*requestedMomentum;
            const double expectedEnergy = scale*requestedEnergy;
            const double conservationError = std::max
            (
                std::max
                (
                    relativeDifference
                    (
                        appliedMomentum.x(), expectedMomentum.x()
                    ),
                    relativeDifference
                    (
                        appliedMomentum.y(), expectedMomentum.y()
                    )
                ),
                std::max
                (
                    relativeDifference
                    (
                        appliedMomentum.z(), expectedMomentum.z()
                    ),
                    relativeDifference(appliedEnergy, expectedEnergy)
                )
            );
            maximumFeedbackConservationError = std::max
            (
                maximumFeedbackConservationError, conservationError
            );
            maximumVelocityChange = std::max
            (
                maximumVelocityChange, windowMaximumVelocityChange
            );
            maximumTemperatureChange = std::max
            (
                maximumTemperatureChange, windowMaximumTemperatureChange
            );
            minimumFeedbackScale = std::min(minimumFeedbackScale, scale);
            ++completedWindows;
            Foam::Info<< "GATE3E_WINDOW role=continuum"
                      << " window=" << completedWindows - 1
                      << " step=" << couplingStep
                      << " feedback_scale=" << scale
                      << " conservation_rel=" << conservationError
                      << " max_delta_U=" << windowMaximumVelocityChange
                      << " max_delta_T=" << windowMaximumTemperatureChange
                      << " adaptive_layer_changes=" << adaptiveLayerChanges
                      << Foam::endl;
        }
#else
        ++couplingStep;
        const gate1b::State localState =
            continuumState(mesh, rho, rhoU, rhoE, T, p, U);
        gate1b::pushState(interface, "continuum_", localState);
        interface.commit(couplingStep);
        const gate1b::State dsmcState =
            gate1b::fetchState(interface, "dsmc_", couplingStep);

        if (!localState.physical() || !dsmcState.physical())
        {
            Foam::Info<< "GATE1B_FAIL role=continuum reason=nonphysical_state"
                      << Foam::endl;
            return 2;
        }

        const double invariantError = conservationError
        (
            continuumConserved(mesh, rho, rhoU, rhoE),
            initial
        );
        const double crossError =
            gate1b::relativeStateError(localState, dsmcState);
        maxConservationError = std::max(maxConservationError, invariantError);
        maxCrossStateError = std::max(maxCrossStateError, crossError);

        Foam::Info<< "GATE1B_CONTINUUM_STEP step=" << couplingStep
                  << " conservation_rel=" << invariantError
                  << " cross_state_rel=" << crossError
                  << " rho=" << localState.rho
                  << " T=" << localState.temperature << Foam::endl;
#endif

        runTime.write();
        runTime.printExecutionTime(Foam::Info);
    }

#ifdef GATE3E_LIVE
    const bool pass =
        couplingStep == gate3e::kineticSteps
     && completedWindows == gate3e::couplingWindows
     && adaptiveLayerChanges > 0
     && maximumFeedbackConservationError <= 1.0e-12
     && maximumVelocityChange > 0.0
     && maximumTemperatureChange > 0.0
     && minimumFeedbackScale > 0.0;
    Foam::Info<< (pass ? "GATE3E_PASS" : "GATE3E_FAIL")
              << " role=continuum_live"
              << " steps=" << couplingStep
              << " windows=" << completedWindows
              << " full_rhoCentralFoam_time_advance=true"
              << " two_way_feedback_applied=true"
              << " adaptive_sampling_surface=true"
              << " adaptive_layer_changes=" << adaptiveLayerChanges
              << " min_feedback_scale=" << minimumFeedbackScale
              << " max_conservation_rel="
              << maximumFeedbackConservationError
              << " max_delta_U=" << maximumVelocityChange
              << " max_delta_T=" << maximumTemperatureChange
              << Foam::endl;
#else
    const bool pass =
        couplingStep >= 5
     && maxConservationError <= conservationTolerance
     && maxCrossStateError <= crossStateTolerance;

    Foam::Info<< (pass ? "GATE1B_PASS" : "GATE1B_FAIL")
              << " role=continuum steps=" << couplingStep
              << " max_conservation_rel=" << maxConservationError
              << " max_cross_state_rel=" << maxCrossStateError
              << Foam::endl;
#endif

    return pass ? 0 : 2;
}
