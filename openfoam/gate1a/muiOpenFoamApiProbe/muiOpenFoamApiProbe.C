// SPDX-License-Identifier: GPL-3.0-or-later
#include "fvCFD.H"
#include "dsmcCloud.H"
#include "mui.h"

#include "muiFoam/CouplingState.hpp"

namespace muiGate1a
{

void publishContinuumPatch
(
    const Foam::fvMesh& mesh,
    const Foam::volScalarField& rho,
    const Foam::volVectorField& velocity,
    const Foam::volScalarField& temperature,
    const Foam::label patchIndex,
    mui::uniface3d& interface,
    const int timeIndex
)
{
    const Foam::vectorField& centres =
        mesh.Cf().boundaryField()[patchIndex];
    const Foam::fvPatchScalarField& patchRho =
        rho.boundaryField()[patchIndex];
    const Foam::fvPatchVectorField& patchVelocity =
        velocity.boundaryField()[patchIndex];
    const Foam::fvPatchScalarField& patchTemperature =
        temperature.boundaryField()[patchIndex];

    forAll(centres, faceIndex)
    {
        const Foam::vector& centre = centres[faceIndex];
        const Foam::vector& u = patchVelocity[faceIndex];
        mui::point3d point;
        point[0] = centre.x();
        point[1] = centre.y();
        point[2] = centre.z();
        interface.push("rho", point, patchRho[faceIndex]);
        interface.push("Ux", point, u.x());
        interface.push("Uy", point, u.y());
        interface.push("Uz", point, u.z());
        interface.push("T", point, patchTemperature[faceIndex]);
    }
    interface.commit(timeIndex);
}

void addDsmcParcelThroughV2312Api
(
    Foam::dsmcCloud& cloud,
    const Foam::point& position,
    const Foam::label cellIndex,
    const Foam::vector& velocity,
    const Foam::scalar internalEnergy,
    const Foam::label typeId
)
{
    cloud.addNewParcel
    (
        position,
        cellIndex,
        velocity,
        internalEnergy,
        typeId
    );
}

} // namespace muiGate1a

int main(int, char**)
{
    // Compiling and linking the two functions above is the API contract test.
    // Gate 1B instantiates them inside the running solvers.
    Foam::Info
        << "GATE1A_OPENFOAM_API_PASS continuum=boundaryFields"
        << " dsmc=addNewParcel mui=uniface3d" << Foam::endl;
    return 0;
}
