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

#include <algorithm>
#include <cmath>

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
    const Foam::volScalarField& temperature
)
{
    const Conserved totals = continuumConserved(mesh, rho, rhoU, rhoE);
    double volume = 0.0;
    double temperatureVolume = 0.0;
    forAll(mesh.V(), celli)
    {
        volume += mesh.V()[celli];
        temperatureVolume += temperature[celli]*mesh.V()[celli];
    }

    gate1b::State state;
    state.rho = totals.mass/volume;
    state.ux = totals.momentum.x()/totals.mass;
    state.uy = totals.momentum.y()/totals.mass;
    state.uz = totals.momentum.z()/totals.mass;
    state.temperature = temperatureVolume/volume;
    state.specificEnergy = totals.energy/totals.mass;
    return state;
}

double conservationError(const Conserved& current, const Conserved& initial)
{
    const double massError =
        std::abs(current.mass - initial.mass)/initial.mass;
    const double energyError =
        std::abs(current.energy - initial.energy)/initial.energy;
    const double momentumScale = std::max
    (
        initial.mass,
        Foam::mag(initial.momentum)
    );
    const double momentumError =
        Foam::mag(current.momentum - initial.momentum)/momentumScale;
    return std::max(massError, std::max(energyError, momentumError));
}

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

    mui::uniface3d interface("mpi://continuum/gate1b");
    const Conserved initial = continuumConserved(mesh, rho, rhoU, rhoE);
    const gate1b::State initialState =
        continuumState(mesh, rho, rhoU, rhoE, T);

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

    while (runTime.run())
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

        ++couplingStep;
        const gate1b::State localState =
            continuumState(mesh, rho, rhoU, rhoE, T);
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

        runTime.write();
        runTime.printExecutionTime(Foam::Info);
    }

    const bool pass =
        couplingStep >= 5
     && maxConservationError <= conservationTolerance
     && maxCrossStateError <= crossStateTolerance;

    Foam::Info<< (pass ? "GATE1B_PASS" : "GATE1B_FAIL")
              << " role=continuum steps=" << couplingStep
              << " max_conservation_rel=" << maxConservationError
              << " max_cross_state_rel=" << maxCrossStateError
              << Foam::endl;

    return pass ? 0 : 2;
}
