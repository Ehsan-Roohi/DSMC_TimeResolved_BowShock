// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"
#include "Gate1BMui.H"

#include <algorithm>
#include <cmath>

namespace
{

const double boltzmann = 1.380649e-23;
const double conservationTolerance = 1.0e-10;
const double crossStateTolerance = 1.0e-3;

struct Conserved
{
    double mass;
    Foam::vector momentum;
    double energy;
};

double meshVolume(const Foam::fvMesh& mesh)
{
    double volume = 0.0;
    forAll(mesh.V(), celli)
    {
        volume += mesh.V()[celli];
    }
    return volume;
}

Conserved conserved(const Foam::dsmcCloud& cloud)
{
    Conserved result;
    result.mass = cloud.massInSystem();
    result.momentum = cloud.linearMomentumOfSystem();
    result.energy =
        cloud.linearKineticEnergyOfSystem()
      + cloud.internalEnergyOfSystem();
    return result;
}

gate1b::State cloudState(const Foam::dsmcCloud& cloud, const double volume)
{
    const Conserved totals = conserved(cloud);
    gate1b::State state;
    state.rho = totals.mass/volume;
    state.ux = totals.momentum.x()/totals.mass;
    state.uy = totals.momentum.y()/totals.mass;
    state.uz = totals.momentum.z()/totals.mass;

    const double bulkEnergy =
        0.5*Foam::magSqr(totals.momentum)/totals.mass;
    const double thermalEnergy =
        cloud.linearKineticEnergyOfSystem() - bulkEnergy;
    const double realMolecules =
        totals.mass/cloud.constProps(0).mass();
    state.temperature =
        2.0*thermalEnergy/(3.0*realMolecules*boltzmann);
    state.specificEnergy = totals.energy/totals.mass;
    return state;
}

bool matchCloudToContinuum
(
    Foam::dsmcCloud& cloud,
    const gate1b::State& target
)
{
    if (!target.physical() || cloud.typeIdList().size() != 1)
    {
        return false;
    }

    const double moleculeMass = cloud.constProps(0).mass();
    const double thermalSpeed =
        std::sqrt(3.0*boltzmann*target.temperature/moleculeMass);
    const Foam::vector targetVelocity(target.ux, target.uy, target.uz);

    // Replace the stochastic initializer with six equal-weight particles per
    // cell. Their symmetric velocities exactly reproduce the monatomic
    // Maxwellian mass, momentum and translational-energy moments.
    cloud.clear();
    forAll(cloud.mesh().C(), celli)
    {
        const Foam::vector position = cloud.mesh().C()[celli];
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity + Foam::vector(thermalSpeed, 0, 0), 0.0, 0
        );
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity - Foam::vector(thermalSpeed, 0, 0), 0.0, 0
        );
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity + Foam::vector(0, thermalSpeed, 0), 0.0, 0
        );
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity - Foam::vector(0, thermalSpeed, 0), 0.0, 0
        );
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity + Foam::vector(0, 0, thermalSpeed), 0.0, 0
        );
        cloud.addNewParcel
        (
            position, celli,
            targetVelocity - Foam::vector(0, 0, thermalSpeed), 0.0, 0
        );
    }

    return cloudState(cloud, meshVolume(cloud.mesh())).physical();
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
        "Gate 1B dsmcFoam with live MUI equilibrium handoff and audit"
    );

    #define NO_CONTROL
    #include "postProcess.H"
    #include "addCheckCaseOptions.H"
    #include "setRootCaseLists.H"
    #include "createTime.H"
    #include "createMesh.H"
    #include "createFields.H"

    const double volume = meshVolume(mesh);
    if (!(volume > 0.0) || dsmc.size() == 0 || dsmc.typeIdList().size() != 1)
    {
        Foam::Info<< "GATE1B_FAIL role=dsmc reason=invalid_initial_cloud"
                  << Foam::endl;
        return 2;
    }

    mui::uniface3d interface("mpi://dsmc/gate1b");

    gate1b::pushState(interface, "dsmc_", cloudState(dsmc, volume));
    interface.commit(0);
    const gate1b::State continuumInitial =
        gate1b::fetchState(interface, "continuum_", 0);

    if (!matchCloudToContinuum(dsmc, continuumInitial))
    {
        Foam::Info<< "GATE1B_FAIL role=dsmc reason=handoff_rebalance"
                  << Foam::endl;
        return 2;
    }

    const Conserved initial = conserved(dsmc);
    const gate1b::State matchedInitial = cloudState(dsmc, volume);
    const double initialCrossError =
        gate1b::relativeStateError(matchedInitial, continuumInitial);

    Foam::Info<< "GATE1B_DSMC_HANDOFF parcels=" << dsmc.size()
              << " initial_cross_rel=" << initialCrossError << Foam::endl;

    int couplingStep = 0;
    double maxConservationError = 0.0;
    double maxCrossStateError = initialCrossError;

    while (runTime.loop())
    {
        ++couplingStep;
        Foam::Info<< "Time = " << runTime.timeName() << Foam::nl << Foam::endl;

        dsmc.evolve();
        dsmc.info();

        const gate1b::State localState = cloudState(dsmc, volume);
        gate1b::pushState(interface, "dsmc_", localState);
        interface.commit(couplingStep);
        const gate1b::State continuumState =
            gate1b::fetchState(interface, "continuum_", couplingStep);

        if (!localState.physical() || !continuumState.physical())
        {
            Foam::Info<< "GATE1B_FAIL role=dsmc reason=nonphysical_state"
                      << Foam::endl;
            return 2;
        }

        const double invariantError =
            conservationError(conserved(dsmc), initial);
        const double crossError =
            gate1b::relativeStateError(localState, continuumState);
        maxConservationError = std::max(maxConservationError, invariantError);
        maxCrossStateError = std::max(maxCrossStateError, crossError);

        Foam::Info<< "GATE1B_DSMC_STEP step=" << couplingStep
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
              << " role=dsmc steps=" << couplingStep
              << " parcels=" << dsmc.size()
              << " max_conservation_rel=" << maxConservationError
              << " max_cross_state_rel=" << maxCrossStateError
              << Foam::endl;

    return pass ? 0 : 2;
}
